"""Study-local accounting for four in-flight requests; prior unknown outcomes stay blocked.

The durable event schema, usage validation, cache and settlement remain inherited
from the frozen client. Only fresh reservations issued by this ledger instance
may coexist. A reopened ledger cannot relabel an old pending call as in flight.
"""
import uuid
from budget_client import GlobalLedger, LedgerError, BudgetStop


class ConcurrentLedger(GlobalLedger):
    def __init__(self,path):
        super().__init__(path)
        self._session_reservations=set()

    async def reserve(self, *, owner, token_cap, fingerprint, request_key, request_hash,
                      phase, input_tokens, max_output, selector_reserve,
                      requested_max_output, cache_file, retry_index):
        await self.initialize()
        async with self._lock:
            expected={'owner':list(owner),'token_cap':token_cap,'fingerprint':fingerprint}
            if owner in self._owners:
                if any(self._owners[owner].get(k)!=v for k,v in expected.items()):
                    raise LedgerError('owner_configuration_changed_on_resume')
            else:
                event={'event':'owner',**expected}
                self._append(event);self._owners[owner]=event
            key=(*owner,request_key)
            if key in self._keys:
                row=self._calls[self._keys[key]]
                if row['request_hash']!=request_hash:raise LedgerError('cached_request_hash_mismatch')
                return dict(row),True
            records=self.owner_records(*owner)
            if any(r.get('usage_issues') for r in records):
                raise BudgetStop('tokenizer_or_provider_usage_mismatch')
            if any(r['status']!='completed_with_usage' and not (
                    r['status']=='reserved' and r['call_id'] in self._session_reservations)
                   for r in records):
                raise BudgetStop('unresolved_prior_request')
            # Held reservations still count toward any declared token ceiling.
            used=sum(self.accounted_tokens(r) for r in records)
            reserve=input_tokens+max_output
            selector=0 if phase=='selector' else selector_reserve
            if token_cap is not None and used+reserve+selector>token_cap:
                raise BudgetStop('tokens',accounted_tokens=used,request_tokens=reserve,
                                 selector_reserve=selector,token_cap=token_cap)
            if max_output<=0:raise BudgetStop('no_output_budget')
            row={'event':'reserve','call_id':uuid.uuid4().hex,'owner':list(owner),
                 'request_key':request_key,'request_hash':request_hash,'phase':phase,
                 'input_tokens':input_tokens,'max_output_tokens':max_output,
                 'requested_max_output_tokens':requested_max_output,'reserved_tokens':reserve,
                 'selector_reserve':selector,'retry_index':retry_index,'cache_file':cache_file}
            self._append(row)
            self._calls[row['call_id']]={**row,'status':'reserved'}
            self._keys[key]=row['call_id'];self._session_reservations.add(row['call_id'])
            return dict(self._calls[row['call_id']]),False
