# Field mapping report — basic_education_department (Department of Basic Education)

- Generated: 2026-10-07 09:55 UTC
- Submission: ..\Datasets\Kanya Sumangla Portal.xlsx
- Catalog: local registry (excluding revenue_department, women_and_child_development_department, health_department, basic_education_department, social_welfare_department)

## Headline

- Fields: **50** in 5 table(s)
- Map to an existing field: **6** (12%)
- Candidates needing confirmation: **6**
- New fields: **38**
- Missing `business_description` on the submission: **0**
- Missing `tag` on the submission: **50**

## Notes
- Compared against the local registry with the five Sumangla departments excluded: those tables were published from this same workbook on 2026-10-07, so 'new' below means 'not seen from Agriculture or PWD', i.e. genuinely new to the platform.
- All 387 fields are already published locally under department + dataset + sheet-derived table; this report exists to show which of them overlap other departments' schemas and which metadata the department still owes us.

## By department

| department | tables | fields | mapped | candidate | new | desc gaps | tag gaps |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| basic_education_department | 5 | 50 | 6 | 6 | 38 | 0 | 50 |

## Candidates to confirm

- `udise_school_master.school_name` ~ `agriculture_department.farmer_registration_master_dataset.farmers.name` (token-overlap)
- `udise_school_master.hos_name` ~ `agriculture_department.farmer_registration_master_dataset.farmers.name` (token-overlap)
- `udise_infrastructure.building_status` ~ `agriculture_department.distribution_record_dataset.current_booking.status` (token-overlap)
- `udise_teacher_profile.teacher_name` ~ `agriculture_department.farmer_registration_master_dataset.farmers.name` (token-overlap)
- `udise_student_profile.student_name` ~ `agriculture_department.farmer_registration_master_dataset.farmers.name` (token-overlap)
- `udise_student_profile.mother_name` ~ `agriculture_department.farmer_registration_master_dataset.farmers.name` (token-overlap)

## Needs fixing before ingest

- `udise_school_master.district_name`: length 100 != existing None; nullable False != existing True
- `udise_school_master.block_name`: length 100 != existing None; nullable False != existing True
- `udise_school_master.pin_code`: type character != existing integer; length 6 != existing None; nullable False != existing True
- `udise_teacher_profile.gender`: length 1 != existing None; nullable False != existing True
- `udise_student_profile.gender`: length 1 != existing None; nullable False != existing True
- `udise_student_profile.father_name`: length 150 != existing None; nullable False != existing True
