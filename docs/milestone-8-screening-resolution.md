# Screening resolution follow-up — November 2, 2026

**Milestone 8 cannot yet be marked complete.** This follow-up closes five individual financial-threshold questions with conservative, source-backed bounds and follows the open Tesla insurance-regulator route. It does not establish complete non-compliant income for any of the seven unresolved candidates or approve an entry. The remaining exact fact requests are prepared below; none has been sent.

The full independent financial/business review remains required before virtual entries. AAPL, MU and LLY retain their recorded static financial failures. NVDA, MSFT, GOOGL, AMZN, TSLA, META and AVGO retain insufficient-evidence outcomes. There are no approved candidates. A genuinely elapsed forward campaign is also still required for Milestone 8; fixtures, source polls and documentation do not supply elapsed sessions.

## Five financial questions resolved without missing zeroes

Apply the **same FTSE Yasaar v4.6 static research methodology and accounting conventions** as the [company review](milestone-8-independent-company-review.md). The [resolution report](../reports/milestone8-screening-resolution-2026-11-02.json) binds the calculations to exact issuer, balance-sheet date, USD unit, source receipts and disjoint asset classifications. Amounts are **USD millions**.

| Company | Condition | Enclosing upper bound | Assets | Upper-bound ratio | Result for that condition |
| --- | --- | ---: | ---: | ---: | --- |
| NVDA | Recognized carrying debt/assets | 91,288 | 320,272 | 28.5033% | Below 33.333% even if all liabilities were debt |
| GOOGL | Recognized carrying debt/assets | 325,763 | 1,003,312 | 32.4688% | Below 33.333% even if all liabilities were debt |
| AVGO | Cash/interest-bearing assets | 56,355 | 188,148 | 29.9525% | Below 33.333% even if all remaining assets bear interest |
| MSFT | Cash/interest-bearing assets | 235,569 | 779,403 | 30.2243% | Below 33.333% even if all remaining assets bear interest |
| META | Cash/interest-bearing assets | 139,868 | 478,836 | 29.2100% | Below 33.333% even if all remaining assets bear interest |

For NVDA and GOOGL, all recognized carrying debt under the selected convention is a nonnegative subset of total recognized liabilities. Thus an unknown finance-lease component is not needed to prove this **one threshold** when even total liabilities are below it. This does not supply the exact debt numerator or include future undrawn/unrecognized commitments outside the already documented mapping.

For the three cash/interest conditions, start with total assets and subtract only identified **disjoint, non-interest-bearing classes**. Every residual asset is included as potentially interest-bearing. Restricted cash, uncertain financing receivables and opaque other assets are therefore enclosed, rather than set to zero:

- **AVGO:** 188,148 − goodwill 97,801 − net acquired intangibles 26,325 − net PPE 3,144 − inventory 4,523 = **56,355**.
- **MSFT:** 779,403 − goodwill 119,646 − net finite-lived intangibles 17,751 − net PPE 346,844 − inventory 1,835 − separately presented operating-lease ROU assets 30,178 − Note 4 equity investments at recorded basis 27,580 = **235,569**. The equity figure is the recorded-basis column, not cost 29,178. Finance-lease assets in PPE are not subtracted a second time. The uncertain interest-bearing portion of financing receivables is already inside the residual.
- **META:** 478,836 − net PPE 253,222 − separately presented operating-lease ROU assets 26,576 − goodwill 23,421 − nonmarketable equity 32,624 − marketable equity 3,125 = **139,868**. Marketable and nonmarketable equity are separate classes; cash and restricted cash remain inside the remainder.

These proofs rely on the existing convention that physical assets, goodwill/intangibles, operating ROU assets and identified equity are not cash or interest-bearing instruments. Income from an equity investee may still require business/income classification; excluding its equity balance from this asset test does not classify its income as permissible.

The bounds are **not reported exact balances or substitute `FinancialScreen` inputs**. Nothing was submitted to the API or written into approvals. A condition supported by a bound does not establish the other conditions, a complete company pass, official FTSE status or qualified methodology acceptance.

## Tesla: regulator route actually followed

The California Department of Insurance company search and public company profiles identify Tesla Inc Group **5018**:

| Legal entity | NAIC code | Domicile | CDI profile |
| --- | --- | --- | --- |
| Tesla General Insurance, Inc. | 24848 | Arizona | [3688](https://interactive.web.insurance.ca.gov/companyprofile/companyprofile?event=companyProfile&doFunction=getCompanyProfile&eid=3688) |
| Tesla Insurance Company | 24813 | California | [3284](https://interactive.web.insurance.ca.gov/companyprofile/companyprofile?event=companyProfile&doFunction=getCompanyProfile&eid=3284) |
| Tesla Property & Casualty, Inc. | 24821 | California | [3353](https://interactive.web.insurance.ca.gov/companyprofile/companyprofile?event=companyProfile&doFunction=getCompanyProfile&eid=3353) |

Ordinary public sessions were used to select each company, read/acknowledge the public-record disclaimer and request 2026 quarterly statements. **All three returned HTTP 200 HTML stating “There are no Financial Statements to display,” not numerical statements or PDFs.** The 2025 annual routes for Tesla Insurance Company and Tesla General Insurance returned the same message. The Property & Casualty annual route timed out during disclaimer acknowledgement, before a statement was obtained. None of these results means zero premiums, zero revenue or no statements anywhere.

The [NAIC filing page](https://content.naic.org/industry_financial_filing.htm) links its [2025 annual/2026 quarterly deadline schedule](https://content.naic.org/sites/default/files/inline-files/2025%20Annual%202026%20Quarterly%20Finanical%20Statement%20Filing%20Deadlines%2012.19.2025.pdf). Page 5 lists **November 15, 2026** for the quarter ended September 30. As of this November 2 review, that date has not arrived. This is a listed filing deadline, not a guarantee of public availability then or a claim that nobody files early.

[Tesla's insurance support pages](https://www.tesla.com/support/insurance/what-is-tesla-insurance) and linked [terms](https://digitalassets.tesla.com/tesla-contents/image/upload/tesla-insurance-terms-of-service.pdf) add an important distinction: Tesla Insurance Services, Inc. is a licensed/appointed **insurance agent**. The group also has the insurers above. Agency commissions, written/earned premiums, reinsurance and intercompany amounts must be reconciled to consolidated GAAP revenue; summing insurer premiums alone would not do that.

The [Q3 2026 issuer update](https://assets-ir.tesla.com/tesla-contents/IR/TSLA-Q3-2026-Update.pdf) was retrieved separately from the previously read SEC exhibit. It says Services/other gross-profit growth was driven by charging, insurance and parts; its financial tables still aggregate Services/other revenue. It does not disclose standalone consolidated insurance revenue. The exact nine-month numerator, overlap with interest 1,301 and the remaining 2,632.45 income capacity therefore remain unresolved. An older statutory figure or a deadline cannot replace that missing current-period fact.

## Seven exact primary-evidence requests — prepared, not sent

For every request, supply the indicated **issuer-consolidated current period**, USD amounts, source accession/URL and table, gross returns separately from borrowing costs/losses, and a bridge removing overlaps. A third-party public badge, product list or unsupported zero is not a response to the numerical request. No recipient is impersonated and no issuer/regulator message or records request was sent.

| Candidate | Current income period | Exact remaining information needed |
| --- | --- | --- |
| NVDA | Jan 26–Jul 26, 2026 | Recognized income from infrastructure-financier equity-method investments, conventional/other finance classification, and classified non-compliant investee/financial returns within the equity/other-income families. “Not significant” supplies no exact amount. The debt threshold now has a supported upper-bound proof. |
| MSFT | Jul 1–Sep 30, 2026 | Interest/dividend split within 744, financing-program income and directly prohibited content/ad/financial-investee income, with gross/net and overlap reconciliation. An exact interest-bearing fraction of financing receivables is no longer needed for the cash/interest threshold proof, but earned financing income still matters. |
| GOOGL | Jan 1–Sep 30, 2026 | Recognized prohibited music/cinema, relevant ads and platform commissions inside mixed YouTube/subscription/platform categories, plus classified investment returns beyond the identified 4,751. The debt threshold now has a supported upper-bound proof. |
| AMZN | Jan 1–Sep 30, 2026 | Category-level prohibited-goods sales and related commissions/fees, cinema/music income and Prime allocation; gross positive conventional-debt returns and convertible-note conversion timing/overlaps beyond the identified 8,091. Issuer IR material does not replace that consolidated attribution. |
| TSLA | Jan 1–Sep 30, 2026 | Consolidated earned insurance revenue/agency commissions, loan charges and earned lease-finance income; subsidiary statutory-to-GAAP, reinsurance/intercompany and gross-interest overlap bridge. The regulator identities and availability limitations are now sourced above. |
| META | Jan 1–Sep 30, 2026 | Recognized prohibited ad/content and classified investee/financial returns beyond gross interest 2,538; current/noncurrent finance-lease liability for the debt mapping. Cash/interest assets now have a supported upper-bound proof. |
| AVGO | Nov 3, 2025–Aug 2, 2026 | Gross interest and classified financial returns embedded in other income, net 649; any separate financing liabilities; revenue from products actually constituting prohibited manufacturing. The 315 tax reversal is not interest. Opaque other assets no longer prevent the cash/interest threshold proof. |

The machine-readable report preserves each earlier source-section search and primary-evidence request, and narrows it for the new findings. Public regulator/issuer disclosures may still resolve parts, especially later statutory data; **public research is not claimed exhausted**. But the currently retrieved records do not contain the needed consolidated income partitions. Completing the actual numerator requires additional primary disclosure or a source-backed qualified evidence package; there is no authorized calculation that turns the missing partitions into zero.

## Access and verification limits

Direct investor-relations pages were attempted for all seven. Six returned public landing pages; the attempted MSFT fiscal-quarter URL returned 404. The Tesla update was followed and inspected. Landing-page HTTP success is not evidence of a new financial split. Google returned JavaScript challenge pages, DuckDuckGo a bot challenge, and Bing returned broad company results unrelated to the detailed queries; those outputs were not used as quantitative company evidence. The precise receipt/status records distinguish these access observations from actual primary disclosures.

CI for **`065a27ff205f51f9c2da803277d1a785bad3b875`** was separately checked: [run 41479069912](https://github.com/MohammedTeir/halal-quant/actions/runs/41479069912) succeeded with **703 PostgreSQL tests passed**. That is the previous commit's result, not an assertion about this follow-up's CI.

The new bound arithmetic helper grants no approval and does not establish its callers' accounting premises. Focused tests cover strict/inclusive boundaries, missing upper/lower bounds, inconsistent/nonfinite/negative inputs and the enclosing-liabilities proof. They pass **44 focused screening tests**, including 14 new cases. Existing full-company screening and entry gates remain intact. Real custody/dividend receipts remain scoped to live readiness; paper ownership is virtual ledger cash/holdings/settlement.

Final local regression result: **715 passed, 2 PostgreSQL-only skips**, with the existing Starlette/httpx deprecation warning. Lint/formatting and diff checks pass. The new receipt archives and all five baseline filing hashes were verified; the five upper-bound identities and ratios were independently recalculated with Decimal precision 60. Seven complete-income values remain explicitly unknown and all approvals/entry authorizations remain false. The old offline checkout remains unchanged at `9991fcf`.
