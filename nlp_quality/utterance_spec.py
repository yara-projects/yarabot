"""Human-reviewed phrase candidates and unseen evaluation utterances.

Candidate and held-out wording are deliberately separate.  The held-out
examples are never read by the promotion script.
"""


def _items(candidate, held_out):
    return {
        "candidate": [value.strip() for value in candidate.split("|")],
        "held_out": [value.strip() for value in held_out.split("|")],
    }


UTTERANCES = {
    "attendance": _items(
        "attendance so far|present percentage|absence count for me|have i missed many days|attendance pls",
        "whats my attendance looking like|how often have i been absent",
    ),
    "exam": _items(
        "what exams are coming up|any tests coming up|when do tests start|assessment schedule|exams coming soon",
        "what assessment do i have next|are any of my exams scheduled",
    ),
    "timetable": _items(
        "this weeks timetable|timetable for the week|what lessons are on today|lessons for tomorrow|weekly class plan",
        "what lessons have i got today|show my schedule for this week",
    ),
    "fee": _items(
        "payment balance for me|any school fees outstanding|have my dues been cleared|unpaid school fees|tuition balance",
        "do i still owe the school|is there a payment pending on my account",
    ),
    "period_count": _items(
        "number of lessons today|teaching periods today|whats my teaching load|lessons on my schedule today|total lessons this week",
        "how many lessons am i taking today|count my teaching periods this week",
    ),
    "classes_assigned": _items(
        "which groups do i teach|sections allocated to me|teaching assignments|grades on my roster|my assigned sections",
        "what groups have i been given|show the sections i am responsible for",
    ),
    "total_students": _items(
        "school enrollment count|pupil population|enrollment total|size of student body|students currently enrolled",
        "what is the schools current enrollment|give me the size of the student body",
    ),
    "total_teachers": _items(
        "size of teaching staff|faculty headcount|teaching staff total|staff strength|number of educators",
        "give me the size of the teaching team|what is the current faculty total",
    ),
    "class_wise_count": _items(
        "enrollment by class|student numbers by section|class strength breakdown|section enrollment figures|headcount per grade",
        "split the student count by class|show enrollment for each section",
    ),
    "greeting": _items(
        "hiya|hello nova|salaam nova|morning nova|hey good afternoon",
        "evening nova|hello there nova",
    ),
    "thanks": _items(
        "nice one thanks|got it thank you|that helps|appreciated nova|brilliant thanks",
        "cheers for the answer|okay that was useful thanks",
    ),
    "help": _items(
        "what questions can nova answer|show available features|things i can ask|nova commands|help with school info",
        "what school questions do you understand|show what nova knows about",
    ),
    "identity": _items(
        "whats my registered name|show account profile|student profile info|details on my account|confirm who i am",
        "what information is on my profile|show the details registered for me",
    ),
    "roll_number": _items(
        "whats my admission number|student number|registration number|school id number|enrollment id",
        "which admission number belongs to me|tell me my student id",
    ),
    "my_class": _items(
        "which section am i in|whats my grade section|tell me my section|registered class|my homeroom",
        "what class was i placed in|which grade and section is mine",
    ),
    "next_period": _items(
        "what lesson is after this|class after this one|whats after this period|upcoming lesson|what subject is next",
        "which lesson comes next for me|what have i got after this class",
    ),
    "subject_teacher": _items(
        "who teaches|teacher for this subject|subject instructor|who takes math|whos teaching science",
        "who is taking us for maths|tell me the teacher for biology",
    ),
    "next_class": _items(
        "what do i teach next|where am i teaching next|next lesson i have|class after my current one|upcoming teaching period",
        "which group is next on my schedule|where should i go for my next lesson",
    ),
    "current_class": _items(
        "what am i teaching now|where should i be teaching|lesson im taking now|current teaching assignment|class on now",
        "which group should i have right now|what lesson am i meant to be in",
    ),
    "free_periods": _items(
        "when am i off today|gaps in todays schedule|non teaching periods|which periods are open|when dont i teach",
        "show the gaps between my lessons|when do i have no class today",
    ),
    "periods_remaining": _items(
        "lessons left today|teaching periods left|how many classes are left|remaining lessons|whats left on my schedule",
        "how much teaching do i still have today|count the periods i have left",
    ),
    "teacher_identity": _items(
        "show my staff profile|my employee details|staff id details|what is my employee number|my teacher account",
        "show the details on my staff record|which employee id is mine",
    ),
    "teacher_location": _items(
        "find mr khan|where can i find ms ali|locate a teacher|which room is mr joseph in|current room for ms sara",
        "where should i look for mr khan|tell me where ms ali is now",
    ),
    "classroom_occupant": _items(
        "who is with 10a now|teacher in 9b right now|whats happening in 8c now|who has class 7a|current teacher for 6b",
        "which teacher is inside 10b now|who is taking 9a this period",
    ),
    "free_teachers": _items(
        "available teaching staff|who is not teaching now|teachers without a class|staff free this period|who can cover now",
        "which teacher has no lesson right now|show staff available for cover",
    ),
    "teacher_schedule_lookup": _items(
        "timetable for mr khan|ms ali schedule|show a teachers timetable|when does mr joseph teach|staff timetable lookup",
        "pull up ms alis teaching schedule|what lessons does mr khan have today",
    ),
    "class_timetable_lookup": _items(
        "10a timetable|schedule for grade 9b|class routine for 8c|show 7a periods|timetable of 6b",
        "what is on the schedule for 10b|show todays lessons for grade 9a",
    ),
    "school_wide_subject_teacher": _items(
        "who teaches|math teaching staff|teachers for science|list english teachers|subject faculty list",
        "show everyone who teaches physics|which staff members take biology",
    ),
    "class_teacher_lookup": _items(
        "who teaches 10a|teachers assigned to 9b|subject teachers for 8c|teaching staff for 7a|faculty list for 6b",
        "show every teacher assigned to 10b|who takes the subjects in grade 9a",
    ),
    "class_teacher": _items(
        "whos in charge of my class|homeroom teacher|form teacher|class mentor|teacher responsible for 10a",
        "who is the teacher in charge of our section|name my form tutor",
    ),
    "low_attendance_count": _items(
        "count students under attendance limit|how many have low attendance|attendance shortage count|students below minimum attendance|low attendance total",
        "how many students are short of attendance|count everyone below the attendance cutoff",
    ),
    "pending_fees_count": _items(
        "count students with unpaid fees|how many fee defaulters|outstanding fees student count|students owing fees total|pending payment count",
        "how many students still owe fees|count accounts with school fees due",
    ),
    "teacher_count_by_subject": _items(
        "how many teach math|math teacher count|number of science teachers|count english teachers|teaching staff count for physics",
        "how many staff members teach biology|give me the faculty count for chemistry",
    ),
    "department_free_teachers": _items(
        "available staff in my department|who in my team is free|department teachers off this period|free faculty in my department|which department staff can cover",
        "show available teachers from my department|who on my department team has a gap now",
    ),
    "department_schedule_today": _items(
        "department timetable today|teams teaching plan today|schedule for my department|whats my department doing today|today department roster",
        "show todays plan for my department|what is my departments teaching schedule today",
    ),
    "department_teacher_count": _items(
        "department staff count|how many faculty in my department|size of my teaching team|headcount for my department|teachers in this department total",
        "how large is the staff in my department|give me my departments teacher total",
    ),
    "notices": _items(
        "any new announcements|latest school updates|whats been announced|recent circulars|school bulletin",
        "has the school posted anything new|show me the newest circular",
    ),
    "subjects_offered": _items(
        "list school subjects|curriculum subjects|courses available at school|what can students study|subject choices",
        "which subjects are part of the curriculum|what courses does yara offer",
    ),
    "complaint_feedback": _items(
        "report a teacher privately|submit feedback about a teacher|teacher complaint|i need to report staff conduct|raise a concern about my teacher",
        "i need to tell the vp about a teacher|how do i make a private teacher complaint",
    ),
    "complaint_summary": _items(
        "show unresolved complaints|pending teacher complaints|complaint inbox|recent student concerns|complaint overview",
        "are any student complaints waiting|show the latest private complaints",
    ),
}


# Boundary cases deliberately belong to the expected intent and are never
# candidates for insertion. They expose the pairs most likely to collide.
HARD_NEGATIVES = [
    ("student", "class_teacher", "who is in charge of my class"),
    ("student", "subject_teacher", "who teaches me mathematics"),
    ("principal", "teacher_count_by_subject", "how many mathematics teachers are there"),
    ("principal", "school_wide_subject_teacher", "list every mathematics teacher"),
    ("principal", "total_teachers", "how many teachers work at the school"),
    ("student", "exam", "when is my next examination"),
    ("student", "timetable", "what lessons do i have this week"),
    ("student", "fee", "is my fee payment still due"),
    ("principal", "pending_fees_count", "how many students have fees due"),
    ("teacher", "next_class", "what class do i teach next"),
    ("teacher", "current_class", "what class should i be teaching now"),
    ("teacher", "period_count", "how many lessons do i teach today"),
    ("teacher", "periods_remaining", "how many lessons do i have left today"),
    ("teacher", "free_periods", "when is my free lesson today"),
    ("principal", "teacher_location", "where is ms ali right now"),
    ("principal", "classroom_occupant", "who is teaching 10a right now"),
    ("principal", "teacher_schedule_lookup", "show ms alis timetable"),
    ("principal", "class_timetable_lookup", "show the timetable for 10a"),
    ("principal", "class_teacher_lookup", "show all teachers for 10a"),
    ("principal", "class_teacher", "who is the class teacher for 10a"),
    ("hod", "department_free_teachers", "who in my department is free now"),
    ("hod", "department_schedule_today", "show my departments schedule today"),
    ("hod", "department_teacher_count", "how many teachers are in my department"),
    ("student", "complaint_feedback", "i want to report a teacher"),
    ("vice_principal", "complaint_summary", "show pending student complaints"),
]


# Short training fragments derived from failure *patterns*, not copies of the
# held-out sentences. They let the substring scorer generalize across wrappers
# and word order without adding subject-specific entries.
GENERALIZERS = {
    "attendance": "my attendance looking|often have i been absent",
    "exam": "assessment do i have next|my exams scheduled",
    "timetable": "lessons have i got|my schedule for this week",
    "fee": "i still owe the school|payment pending on my account",
    "period_count": "how many lessons|count my teaching periods",
    "classes_assigned": "groups have i been given|sections i am responsible for",
    "total_students": "schools current enrollment|size of the student body",
    "total_teachers": "size of the teaching team|current faculty total",
    "class_wise_count": "student count by class|enrollment for each section",
    "greeting": "evening nova|hello there nova",
    "thanks": "cheers for|useful thanks",
    "help": "school questions|what nova knows",
    "identity": "information on my profile|details registered for me",
    "roll_number": "admission number belongs|my student id",
    "my_class": "class was i placed|my grade and section",
    "next_period": "lesson comes next for me|i got after this class",
    "subject_teacher": "taking us for maths|teacher for biology subject",
    "next_class": "group is next on my schedule|my next lesson",
    "current_class": "group should i have right now|lesson am i meant to be in",
    "free_periods": "gaps between my lessons|i have no class today",
    "periods_remaining": "teaching do i still have today|periods i have left",
    "teacher_identity": "details on my staff record|employee id is mine",
    "teacher_location": "look for mr|where ms ali is now",
    "classroom_occupant": "teacher is inside 10b|taking 9a this period",
    "free_teachers": "teacher has no lesson right now|staff available for cover",
    "teacher_schedule_lookup": "alis teaching schedule|lessons does mr",
    "class_timetable_lookup": "schedule for 10b|lessons for grade",
    "school_wide_subject_teacher": "everyone who teaches|staff members take",
    "class_teacher_lookup": "every teacher assigned|takes the subjects in grade",
    "class_teacher": "teacher in charge of our section|form tutor",
    "low_attendance_count": "students are short of attendance|below the attendance cutoff",
    "pending_fees_count": "students still owe fees|accounts with school fees due",
    "teacher_count_by_subject": "staff members teach|faculty count for",
    "department_free_teachers": "available teachers from my department|department team has a gap",
    "department_schedule_today": "todays plan for my department|departments teaching schedule today",
    "department_teacher_count": "large is the staff in my department|departments teacher total",
    "notices": "posted anything new|newest circular",
    "subjects_offered": "part of the curriculum|courses does yara offer",
    "complaint_feedback": "i need to tell the vp|i make a private teacher complaint",
    "complaint_summary": "student complaints waiting|latest private complaints",
}
