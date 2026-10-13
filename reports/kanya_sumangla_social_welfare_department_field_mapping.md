# Field mapping report — social_welfare_department (Social Welfare Department)

- Generated: 2026-10-07 09:55 UTC
- Submission: ..\Datasets\Kanya Sumangla Portal.xlsx
- Catalog: local registry (excluding revenue_department, women_and_child_development_department, health_department, basic_education_department, social_welfare_department)

## Headline

- Fields: **41** in 7 table(s)
- Map to an existing field: **2** (4%)
- Candidates needing confirmation: **16**
- New fields: **23**
- Missing `business_description` on the submission: **0**
- Missing `tag` on the submission: **15**

## Notes
- Compared against the local registry with the five Sumangla departments excluded: those tables were published from this same workbook on 2026-10-07, so 'new' below means 'not seen from Agriculture or PWD', i.e. genuinely new to the platform.
- All 387 fields are already published locally under department + dataset + sheet-derived table; this report exists to show which of them overlap other departments' schemas and which metadata the department still owes us.

## By department

| department | tables | fields | mapped | candidate | new | desc gaps | tag gaps |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| social_welfare_department | 7 | 41 | 2 | 16 | 23 | 0 | 15 |

## Candidates to confirm

- `cmsvy_application.block_ulb_name` ~ `agriculture_department.distribution_record_dataset.current_booking.block_name` (token-overlap)
- `cmsvy_bride_details.bride_name` ~ `agriculture_department.farmer_registration_master_dataset.farmers.name` (token-overlap)
- `cmsvy_bride_details.bride_father_name` ~ `agriculture_department.distribution_record_dataset.current_booking_farmer_details.father_name` (token-overlap)
- `cmsvy_bride_details.bride_mobile_no` ~ `agriculture_department.distribution_record_dataset.current_booking_farmer_details.mobile_no` (token-overlap)
- `cmsvy_groom_details.groom_name` ~ `agriculture_department.farmer_registration_master_dataset.farmers.name` (token-overlap)
- `cmsvy_groom_details.groom_father_name` ~ `agriculture_department.distribution_record_dataset.current_booking_farmer_details.father_name` (token-overlap)
- `cmsvy_groom_details.groom_district` ~ `agriculture_department.farmer_registration_master_dataset.farmers.district` (token-overlap)
- `cmsvy_groom_details.groom_address` ~ `agriculture_department.distribution_record_dataset.current_booking_farmer_details.address` (token-overlap)
- `cmsvy_eligibility.caste_cert_no` ~ `agriculture_department.farmer_registration_master_dataset.farmers.caste_application_no` (token-overlap)
- `cmsvy_eligibility.bpl_card_no` ~ `agriculture_department.farmer_registration_master_dataset.farmers.rashan_card_no` (token-overlap)
- `cmsvy_bank_details.bride_bank_name` ~ `agriculture_department.farmer_registration_master_dataset.farmers.bank_name` (token-overlap)
- `cmsvy_bank_details.bride_branch_name` ~ `agriculture_department.farmer_registration_master_dataset.farmers.branch_name` (token-overlap)
- `cmsvy_bank_details.bride_ifsc_code` ~ `agriculture_department.farmer_registration_master_dataset.farmers.ifsc_code` (token-overlap)
- `cmsvy_bank_details.bride_account_no` ~ `agriculture_department.scheme_physical_financial_progress_dataset.grant_wise_bill_generation.loan_account_no` (token-overlap)
- `cmsvy_workflow.verification_status` ~ `agriculture_department.distribution_record_dataset.current_booking.status` (token-overlap)
- `cmsvy_workflow.dbt_payment_status` ~ `agriculture_department.distribution_record_dataset.current_booking.payment_status` (token-overlap)

## Needs fixing before ingest

- `cmsvy_application.application_no`: nullable False != existing True
- `cmsvy_application.district`: nullable False != existing True
