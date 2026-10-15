# Field mapping report — health_department (Health Department)

- Generated: 2026-10-07 09:55 UTC
- Submission: ..\Datasets\Kanya Sumangla Portal.xlsx
- Catalog: local registry (excluding revenue_department, women_and_child_development_department, health_department, basic_education_department, social_welfare_department)

## Headline

- Fields: **56** in 4 table(s)
- Map to an existing field: **5** (8%)
- Candidates needing confirmation: **15**
- New fields: **36**
- Missing `business_description` on the submission: **0**
- Missing `tag` on the submission: **26**

## Notes
- Compared against the local registry with the five Sumangla departments excluded: those tables were published from this same workbook on 2026-10-07, so 'new' below means 'not seen from Agriculture or PWD', i.e. genuinely new to the platform.
- All 387 fields are already published locally under department + dataset + sheet-derived table; this report exists to show which of them overlap other departments' schemas and which metadata the department still owes us.

## By department

| department | tables | fields | mapped | candidate | new | desc gaps | tag gaps |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| health_department | 4 | 56 | 5 | 15 | 36 | 0 | 26 |

## Candidates to confirm

- `uwin_cardholder_profile.hof_name` ~ `agriculture_department.farmer_registration_master_dataset.farmers.name` (token-overlap)
- `uwin_cardholder_profile.postal_address` ~ `agriculture_department.distribution_record_dataset.current_booking_farmer_details.address` (token-overlap)
- `uwin_cardholder_profile.taluka_name` ~ `agriculture_department.farmer_registration_master_dataset.farmers.name` (token-overlap)
- `uwin_cardholder_profile.village_name` ~ `agriculture_department.farmer_registration_master_dataset.farmers.name` (token-overlap)
- `uwin_cardholder_profile.ration_card_no` ~ `agriculture_department.farmer_registration_master_dataset.farmers.rashan_card_no` (token-overlap)
- `uwin_cardholder_profile.bpl_card_no` ~ `agriculture_department.farmer_registration_master_dataset.farmers.rashan_card_no` (token-overlap)
- `uwin_cardholder_profile.aadhar_card_no` ~ `agriculture_department.farmer_registration_master_dataset.farmers.aadhar_no` (token-overlap)
- `uwin_attachments.doc_id` ~ `agriculture_department.distribution_record_dataset.current_booking.id` (token-overlap)
- `uwin_attachments.document_name` ~ `agriculture_department.farmer_registration_master_dataset.farmers.name` (token-overlap)
- `uwin_vaccination_ledger.uwin_beneficiary_id` ~ `agriculture_department.scheme_physical_financial_progress_dataset.grant_wise_bill_generation.beneficiary_id` (token-overlap)
- `uwin_vaccination_ledger.opv_birth_date` ~ `agriculture_department.farmer_registration_master_dataset.farmers.date_of_birth` (token-overlap)
- `uwin_vaccination_ledger.hepb_birth_date` ~ `agriculture_department.farmer_registration_master_dataset.farmers.date_of_birth` (token-overlap)
- `uwin_delivery_address.delivery_id` ~ `agriculture_department.distribution_record_dataset.current_booking.id` (token-overlap)
- `uwin_delivery_address.uwin_beneficiary_id` ~ `agriculture_department.scheme_physical_financial_progress_dataset.grant_wise_bill_generation.beneficiary_id` (token-overlap)
- `uwin_delivery_address.taluka_block_name` ~ `agriculture_department.distribution_record_dataset.current_booking.block_name` (token-overlap)

## Needs fixing before ingest

- `uwin_cardholder_profile.gender`: nullable False != existing True
- `uwin_cardholder_profile.district_name`: nullable False != existing True
- `uwin_cardholder_profile.pincode`: type numeric != existing integer; length 6 != existing None; nullable False != existing True
- `uwin_cardholder_profile.mobile_no`: type numeric != existing character varying; length 10 != existing None; nullable False != existing True
- `uwin_delivery_address.district_name`: length 100 != existing None; nullable False != existing True
