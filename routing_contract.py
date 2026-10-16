"""Shared role intent contract. Safe to import without loading the chatbot/AI runtime."""

STAFF_LOOKUP_INTENTS = [
    "teacher_schedule_lookup", "teacher_classes_lookup", "teacher_department",
    "teacher_profile_lookup",
    "school_wide_subject_teacher", "class_teacher_lookup", "class_teacher",
    "department_staff", "department_leadership", "school_leadership",
]

TEACHER_INTENTS = ["period_count", "timetable", "classes_assigned", "next_class",
                    "current_class", "free_periods", "periods_remaining", "teacher_identity",
                    "notices", "subjects_offered", "low_attendance_count",
                    "pending_fees_count"] + STAFF_LOOKUP_INTENTS
HOD_DEPARTMENT_INTENTS = ["department_free_teachers", "department_schedule_today",
                           "department_teacher_count"]

ROLE_PERSONAL_INTENTS = {
    "student": ["attendance", "exam", "timetable", "fee", "identity",
                "roll_number", "my_class", "class_teacher", "next_period",
                "subject_teacher", "class_teacher_lookup", "teacher_department",
                "teacher_profile_lookup", "department_leadership", "school_leadership",
                "notices", "subjects_offered",
                "complaint_feedback"],
    "teacher": TEACHER_INTENTS,
    "parent": ["attendance", "exam", "timetable", "fee", "class_teacher",
               "subject_teacher", "notices", "subjects_offered"],
    "hod": TEACHER_INTENTS + HOD_DEPARTMENT_INTENTS,
    "principal": ["teacher_count_by_subject", "total_students", "total_teachers",
                  "class_wise_count", "teacher_location", "classroom_occupant",
                  "free_teachers", "teacher_schedule_lookup", "class_timetable_lookup",
                  "school_wide_subject_teacher", "class_teacher_lookup", "class_teacher",
                  "teacher_classes_lookup", "teacher_department", "department_staff",
                  "teacher_profile_lookup",
                  "department_leadership", "school_leadership",
                  "department_schedule_today",
                  "low_attendance_count", "pending_fees_count", "notices", "subjects_offered"],
}
