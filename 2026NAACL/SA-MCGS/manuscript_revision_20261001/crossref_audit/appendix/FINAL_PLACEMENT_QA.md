# Final appendix placement QA — passed

Reviewed latest `clean_build/acl_latex_clean.pdf` (26 pages) and `marked_build/acl_latex.pdf` (31 pages), following the prior-table queue adjustment. Current hashes and complete label/page inventory are in `final_placement_qa.json`. This reviewer did not edit or compile.

- Clean Conclusion still ends on page8; Limitations/References begin page9.
- All seven clean figures, nineteen tables, and five algorithms retain their numbers. The two Table12 label aliases remain intentional.
- Appendix float boundaries pass: B expert tables remain before C; C case figure before D; D algorithms before E; F prior table before G; I dataset tables before J; J breakdown table/size/budget figures before K.
- Clean page18 is now well filled: Table11 appears as a normal full-width top-of-page float, followed immediately on that same page by the Appendix F heading/introduction and the beginning of G. A float above its own same-page section heading is normal two-column typesetting, not an ownership failure. The previous near-empty prior-introduction-only page is eliminated, reducing the clean PDF from27 to26 pages.
- Algorithms2–5 flow through D and E begins after Algorithm5; the stranded algorithms-only blank column is eliminated.
- Appendix K's opening has ordinary heading/paragraph spacing after appendix-only ragged-bottom setting.
- No new clipping, overlap, missing object/caption, or altered font/margins observed.

The marked counterpart remains readable: Appendix F begins on p20, its Table12 occupies the top of p21 before G. Marked p20 retains some normal whitespace because tracked deletions change pagination; this is not a clean-submission defect or a reason for further layout changes. Other sparse appendix tails are an acceptable consequence of keeping full-width floats with their owning sections.

Final status: reference numbering, object ownership, main-page limit, and visual QA passed. No further changes recommended for this audit.
