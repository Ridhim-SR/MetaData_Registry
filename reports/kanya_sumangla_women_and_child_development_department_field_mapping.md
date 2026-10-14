# Field mapping report — women_and_child_development_department (Department of Women and Child Development)

- Generated: 2026-10-07 09:55 UTC
- Submission: ..\Datasets\Kanya Sumangla Portal.xlsx
- Catalog: local registry (excluding revenue_department, women_and_child_development_department, health_department, basic_education_department, social_welfare_department)

## Headline

- Fields: **206** in 22 table(s)
- Map to an existing field: **12** (5%)
- Candidates needing confirmation: **39**
- New fields: **155**
- Missing `business_description` on the submission: **1**
- Missing `tag` on the submission: **151**

## Notes
- Compared against the local registry with the five Sumangla departments excluded: those tables were published from this same workbook on 2026-10-07, so 'new' below means 'not seen from Agriculture or PWD', i.e. genuinely new to the platform.
- All 387 fields are already published locally under department + dataset + sheet-derived table; this report exists to show which of them overlap other departments' schemas and which metadata the department still owes us.

## By department

| department | tables | fields | mapped | candidate | new | desc gaps | tag gaps |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| women_and_child_development_department | 22 | 206 | 12 | 39 | 155 | 1 | 151 |

## Candidates to confirm

- `mksy_citizen_registration.login_id` ~ `agriculture_department.distribution_record_dataset.current_booking.id` (token-overlap)
- `mksy_citizen_profile.login_id` ~ `agriculture_department.distribution_record_dataset.current_booking.id` (token-overlap)
- `mksy_citizen_profile.tehsil_name` ~ `agriculture_department.farmer_registration_master_dataset.farmers.name` (token-overlap)
- `mksy_citizen_profile.village_name` ~ `agriculture_department.farmer_registration_master_dataset.farmers.name` (token-overlap)
- `mksy_citizen_bank.login_id` ~ `agriculture_department.distribution_record_dataset.current_booking.id` (token-overlap)
- `mksy_citizen_bank.bank_district` ~ `agriculture_department.farmer_registration_master_dataset.farmers.bank_district_id` (token-overlap)
- `mksy_citizen_bank.branch_address` ~ `agriculture_department.distribution_record_dataset.current_booking_farmer_details.address` (token-overlap)
- `mksy_citizen_bank.pfms_beneficiary_id` ~ `agriculture_department.scheme_physical_financial_progress_dataset.grant_wise_bill_generation.beneficiary_id` (token-overlap)
- `mksy_citizen_aadhaar.login_id` ~ `agriculture_department.distribution_record_dataset.current_booking.id` (token-overlap)
- `mksy_citizen_aadhaar.parivar_id` ~ `agriculture_department.distribution_record_dataset.current_booking.id` (token-overlap)
- `mksy_beneficiary_child.login_id` ~ `agriculture_department.distribution_record_dataset.current_booking.id` (token-overlap)
- `mksy_beneficiary_child.mother_name` ~ `agriculture_department.farmer_registration_master_dataset.farmers.name` (token-overlap)
- `mksy_stage_claim_common.application_status` ~ `agriculture_department.distribution_record_dataset.current_booking.status` (token-overlap)
- `mksy_stage_1_birth.birth_registration_no` ~ `agriculture_department.distribution_record_dataset.current_booking_farmer_details.registration_no` (token-overlap)
- `mksy_stage_3_class_1.school_name` ~ `agriculture_department.farmer_registration_master_dataset.farmers.name` (token-overlap)
- `mksy_stage_3_class_1.school_address` ~ `agriculture_department.distribution_record_dataset.current_booking_farmer_details.address` (token-overlap)
- `mksy_stage_4_class_6.school_name` ~ `agriculture_department.farmer_registration_master_dataset.farmers.name` (token-overlap)
- `mksy_stage_4_class_6.school_address` ~ `agriculture_department.distribution_record_dataset.current_booking_farmer_details.address` (token-overlap)
- `mksy_stage_5_class_9.school_name` ~ `agriculture_department.farmer_registration_master_dataset.farmers.name` (token-overlap)
- `mksy_stage_5_class_9.school_address` ~ `agriculture_department.distribution_record_dataset.current_booking_farmer_details.address` (token-overlap)
- `mksy_stage_6_higher_edu.course_name` ~ `agriculture_department.farmer_registration_master_dataset.farmers.name` (token-overlap)
- `mksy_stage_6_higher_edu.institution_name` ~ `agriculture_department.farmer_registration_master_dataset.farmers.name` (token-overlap)
- `mksy_stage_6_higher_edu.institution_address` ~ `agriculture_department.distribution_record_dataset.current_booking_farmer_details.address` (token-overlap)
- `pmmvy_beneficiary_id.beneficiary_name_id` ~ `agriculture_department.scheme_physical_financial_progress_dataset.grant_wise_bill_generation.beneficiary_id` (token-overlap)
- `pmmvy_beneficiary_id.beneficiary_alt_id_no` ~ `agriculture_department.scheme_physical_financial_progress_dataset.grant_wise_bill_generation.beneficiary_id` (token-overlap)

## Needs fixing before ingest

- `mksy_citizen_profile.district_name`: nullable False != existing True
- `mksy_citizen_profile.block_name`: nullable False != existing True
- `mksy_citizen_profile.pincode`: type numeric != existing integer; length 6 != existing None; nullable False != existing True
- `mksy_citizen_bank.bank_name`: nullable False != existing True
- `mksy_citizen_bank.ifsc_code`: length 11 != existing None; nullable False != existing True
- `mksy_citizen_bank.branch_name`: nullable False != existing True
- `mksy_citizen_bank.bank_account_no`: nullable False != existing True
- `mksy_citizen_aadhaar.aadhaar_number`: Unrecognized Format value '[Aadhaar Redacted]' -- add a rule to FORMAT_TYPE_RULES in field_dictionary_parser.py.
- `mksy_beneficiary_child.date_of_birth`: type date != existing timestamp without time zone; nullable False != existing True
- `mksy_beneficiary_child.father_name`: nullable False != existing True
- `mksy_beneficiary_child.child_aadhaar_no`: Unrecognized Format value '[Aadhaar Redacted]' -- add a rule to FORMAT_TYPE_RULES in field_dictionary_parser.py.
- `mksy_stage_claim_common.application_no`: length 12 != existing None; nullable False != existing True
- `pmmvy_application_details.mobile_no`: type numeric != existing character varying; length 10 != existing None; nullable False != existing True
- `pmmvy_field_verification.district_name`: nullable False != existing True
