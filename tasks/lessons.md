# Lessons & Patterns Registry

## Operational Principles
1. **Candidate Truth Invariant**: Never allow any module to invent, extrapolate, or falsify experience, job titles, or skills.
2. **Salary Eligibility Precision**: Disclosed minimum salary must be $\ge$ 20 LPA. Any range with a lower minimum (e.g. 15-25 LPA) must be rejected immediately without considering the upper bound.
3. **Safe Automation**: Never attempt to bypass CAPTCHA, MFA, or rate limits. Halting and logging `BLOCKED` preserves account integrity.
4. **Idempotency**: Every job processing step must be idempotent and recoverable from SQLite state.

---

## Log of Lessons Learned
*(Entries will be added upon post-implementation review or user feedback)*
