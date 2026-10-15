# Field mapping report — revenue_department (Revenue Department (E-District))

- Generated: 2026-10-07 09:55 UTC
- Submission: ..\Datasets\Kanya Sumangla Portal.xlsx
- Catalog: local registry (excluding revenue_department, women_and_child_development_department, health_department, basic_education_department, social_welfare_department)

## Headline

- Fields: **34** in 1 table(s)
- Map to an existing field: **0** (0%)
- Candidates needing confirmation: **3**
- New fields: **31**
- Missing `business_description` on the submission: **0**
- Missing `tag` on the submission: **23**

## Notes
- Compared against the local registry with the five Sumangla departments excluded: those tables were published from this same workbook on 2026-10-07, so 'new' below means 'not seen from Agriculture or PWD', i.e. genuinely new to the platform.
- All 387 fields are already published locally under department + dataset + sheet-derived table; this report exists to show which of them overlap other departments' schemas and which metadata the department still owes us.

## By department

| department | tables | fields | mapped | candidate | new | desc gaps | tag gaps |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| revenue_department | 1 | 34 | 0 | 3 | 31 | 0 | 23 |

## Candidates to confirm

- `income_certificate_application.mother_name` ~ `agriculture_department.farmer_registration_master_dataset.farmers.name` (token-overlap)
- `income_certificate_application.curr_district_name` ~ `agriculture_department.distribution_record_dataset.current_booking.district_name` (token-overlap)
- `income_certificate_application.permanent_address` ~ `agriculture_department.distribution_record_dataset.current_booking_farmer_details.address` (token-overlap)
