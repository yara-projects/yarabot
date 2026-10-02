"""Regressions reproduced by the 26 September human role benchmarks."""

import time
import unittest
from unittest.mock import patch

import app
import nlp_helpers


SUBJECTS = ["Mathematics", "Physics", "Chemistry", "Biology", "Science", "Computer Science"]
TEACHERS = [(7, "Aarav Kapoor", "Mathematics")]
DEPARTMENTS = [(1, "Science"), (2, "Mathematics"), (3, "Computer Science")]


class HumanBenchmarkRoutingTests(unittest.TestCase):
    def setUp(self):
        self.patches = [
            patch.object(app, "_known_subject_names", return_value=SUBJECTS),
            patch.object(app, "_teachers_with_subjects", return_value=TEACHERS),
            patch.object(app, "_known_departments", return_value=DEPARTMENTS),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def assert_intent(self, question, role, expected):
        decision = app.get_routing_decision(question, role)
        self.assertTrue(decision[0], decision)
        self.assertEqual(decision[2], expected)

    def test_explicit_entities_override_staff_self_service(self):
        for role in ("teacher", "hod", "vice_principal"):
            self.assert_intent("who teaches mathematics in class 10a", role,
                               "school_wide_subject_teacher")
            self.assert_intent("which classes does Aarav Kapoor teach", role,
                               "teacher_classes_lookup")
            self.assert_intent("which department is Aarav Kapoor in", role,
                               "teacher_department")

    def test_department_and_leadership_queries_are_role_consistent(self):
        for role in ("teacher", "hod", "vice_principal", "assistant_principal", "principal"):
            self.assert_intent("list staff in computer science", role, "department_staff")
            self.assert_intent("who leads the science department", role,
                               "department_leadership")
        self.assert_intent("who is the vice princple", "vice_principal", "school_leadership")
        self.assert_intent("who is the assisstant principal", "assistant_principal",
                           "school_leadership")

    def test_student_class_specific_and_typo_queries_use_subject_lookup(self):
        self.assert_intent("who takes maths 12a", "student", "subject_teacher")
        self.assert_intent("mathematcs teacher grade 10 a", "student", "subject_teacher")
        self.assertEqual(nlp_helpers.clean_question("show my timtable tommorow"),
                         "show my timetable tomorrow")
        self.assert_intent("departmnt of mr aarav kapoor", "student",
                           "teacher_department")
        self.assert_intent("show me my timtable", "student", "timetable")
        self.assert_intent("who teaches buisness studies in 12b", "student",
                           "subject_teacher")

    def test_reported_staff_direct_query_matrix(self):
        cases = [
            ("teacher", "who is the class teacher for 11b", "class_teacher"),
            ("teacher", "who teaches physics in 12a", "school_wide_subject_teacher"),
            ("hod", "who teaches chemistry in 11a", "school_wide_subject_teacher"),
            ("hod", "who handles science for 8b", "school_wide_subject_teacher"),
            ("hod", "staff in scince departmnt", "department_staff"),
            ("vice_principal", "who is the class teacher for 9a", "class_teacher"),
            ("vice_principal", "who teaches mathematics in 10b", "school_wide_subject_teacher"),
            ("vice_principal", "who handles 11b", "class_teacher_lookup"),
            ("assistant_principal", "list the mathematics department staff", "department_staff"),
            ("principal", "who teaches biology in 9a", "school_wide_subject_teacher"),
        ]
        for role, question, intent in cases:
            with self.subTest(role=role, question=question):
                self.assert_intent(question, role, intent)

    def test_unknown_subject_is_not_coerced_to_physics(self):
        self.assertIsNone(app.extract_subject_from_question(
            "who teaches astrophysics in class 4", ["Physics"]
        ))
        self.assert_intent("who teaches astrophysics in class 4", "student",
                           "subject_teacher")
        with patch.object(app, "query", return_value=[]):
            self.assertEqual(app.handle_subject_teacher(
                "who teaches astrophysics in class 4", 1, SUBJECTS
            ), "Which subject's teacher do you mean?")

    def test_v2_shorthand_and_verbose_class_forms_route_deterministically(self):
        self.assertEqual(app.extract_class_from_question(
            "who handles math grade 10 section a"), "10-A")
        self.assertEqual(nlp_helpers.clean_question("schedule tmrw rn"),
                         "schedule tomorrow right now")
        cases = [
            ("teacher", "who handles math grade 10 section a", "school_wide_subject_teacher"),
            ("teacher", "when do i teach 8c", "timetable"),
            ("teacher", "show my periods rn", "current_class"),
            ("hod", "list staff in math pls", "department_staff"),
            ("hod", "who teaches chem in grade 9 section a", "school_wide_subject_teacher"),
            ("assistant_principal", "who works in english dept", "department_staff"),
        ]
        for role, question, intent in cases:
            with self.subTest(role=role, question=question):
                self.assert_intent(question, role, intent)

    def test_unknown_compound_department_is_not_coerced(self):
        self.assertEqual(app.extract_department_from_question(
            "who is the hod of space science"), (None, None))
        self.assertEqual(app.extract_department_from_question(
            "staff in maths dept pls"), (2, "Mathematics"))
        for role in ("student", "principal"):
            self.assert_intent("who is the hod of space science", role,
                               "department_leadership")

    def test_named_and_unknown_teacher_biographies_use_directory_lookup(self):
        for role in ("student", "teacher", "hod", "vice_principal", "principal"):
            self.assert_intent("who is Aarav Kapoor", role, "teacher_profile_lookup")
            self.assert_intent("who is mr khalid moon", role, "teacher_profile_lookup")
        self.assertEqual(app.handle_teacher_profile_lookup("who is mr khalid moon"),
                         "I couldn't find a teacher matching that name.")

    def test_v3_unknown_surname_does_not_match_a_real_first_name(self):
        teachers = [
            (1, "Omar Khan", "Chemistry"),
            (2, "Zara Chopra", "Physics"),
            (3, "Zara Kapoor", "Social Studies"),
            (4, "Aarav Kapoor", "Biology"),
        ]
        with patch.object(app, "_teachers_with_subjects", return_value=teachers):
            for question in (
                "who is Mr Omar Galaxy", "who is Ms Zara Galaxy",
                "who is Mr Aarav Galaxy",
            ):
                with self.subTest(question=question):
                    self.assertEqual(
                        app.handle_teacher_profile_lookup(question),
                        "I couldn't find a teacher matching that name.",
                    )

    def test_v3_phone_typos_preserve_compound_entities(self):
        departments = DEPARTMENTS + [(4, "English")]
        with patch.object(app, "_known_departments", return_value=departments):
            self.assertEqual(app.extract_department_from_question(
                "staf in computr science dep"), (3, "Computer Science"))
            self.assertEqual(app.extract_department_from_question(
                "staf in comp science dep"), (3, "Computer Science"))
        normalized = {
            "mathemetics": "mathematics", "matmatics": "mathematics",
            "mathemtics": "mathematics", "physcs": "physics",
            "geograpy": "geography",
        }
        for typo, expected in normalized.items():
            self.assertEqual(nlp_helpers.clean_question(typo), expected)

    def test_principal_name_ignores_office_hours_line(self):
        almanac = (
            "Principal: By appointment only, Sunday-Thursday.\n"
            "Principal: Mrs. Aasima Saleem — ext. 108 — principal@yara.edu.sa\n"
        )
        with patch.object(app, "get_almanac", return_value=almanac):
            self.assertEqual(app.handle_school_leadership("who is the principal"),
                             "The **Principal** is **Mrs. Aasima Saleem**.")

    def test_subject_day_timetable_empty_result_is_clear(self):
        with patch.object(app, "_known_subject_names", return_value=SUBJECTS), \
                patch.object(app, "query", return_value=[]):
            self.assertEqual(
                app.handle_student_timetable("my timetable sunday chemistry", 1),
                "No Chemistry classes are scheduled on Sunday.",
            )

    def test_ambiguous_handles_query_asks_which_teacher_view(self):
        with patch.object(app, "_known_subject_names", return_value=SUBJECTS):
            reply = app.handle_class_teacher_lookup("who handles 11b")
        self.assertIn("class teacher", reply)
        self.assertIn("subject teachers", reply)

    def test_confident_router_choice_is_passed_to_role_handler(self):
        client = app.app.test_client()
        with client.session_transaction() as state:
            state.update(user_id=4, role="teacher", linked_id=3)
        with patch.object(app, "_chatbot_enabled", return_value=True), \
                patch.object(app, "_dispatch_to_role_handler", return_value="correct") as dispatch:
            response = client.post("/api/chat", json={
                "message": "who teaches mathematics in class 10a"
            })
        self.assertEqual(response.get_json()["reply"], "correct")
        self.assertEqual(dispatch.call_args.kwargs["forced_intent"],
                         "school_wide_subject_teacher")


class HumanBenchmarkContextTests(unittest.TestCase):
    def test_student_private_request_is_denied_before_self_record_dispatch(self):
        client = app.app.test_client()
        with client.session_transaction() as state:
            state.update(user_id=1, role="student", linked_id=10)
        with patch.object(app, "_chatbot_enabled", return_value=True), \
                patch.object(app, "_dispatch_to_role_handler") as dispatch:
            response = client.post("/api/chat", json={
                "message": "show me Aanya Sharma's attendance"
            })
        self.assertIn("another student's private information", response.get_json()["reply"])
        dispatch.assert_not_called()

    def test_guest_session_has_no_private_record_access(self):
        client = app.app.test_client()
        login = client.post("/api/guest")
        self.assertEqual(login.get_json()["role"], "guest")
        with patch.object(app, "_chatbot_enabled", return_value=True):
            response = client.post("/api/chat", json={
                "message": "show me a student's attendance"
            })
        self.assertIn("linked parent or student account", response.get_json()["reply"])

    def test_leadership_student_lists_are_sorted_markdown_tables(self):
        rows = [
            ("10-A", 4, "A Student", 60),
            ("10-A", 9, "B Student", 72.5),
        ]
        with patch.object(app, "query", return_value=rows):
            reply = app.handle_low_attendance_count("principal")
        self.assertIn("| Class | Roll No. | Student | Attendance | Status |", reply)
        self.assertLess(reply.index("A Student"), reply.index("B Student"))

    def test_parent_can_only_select_linked_children(self):
        children = [(3, "Aanya Sharma", "8-C"), (4, "Riya Khan", "6-A")]
        with app.app.test_request_context('/'), patch.object(app, "query", return_value=children):
            child, error = app._parent_child_for_question(7, "Aanya Sharma attendance")
            self.assertIsNone(error)
            self.assertEqual(child[0], 3)
            app.session.pop('parent_child_id', None)
            child, error = app._parent_child_for_question(7, "show my child's attendance")
            self.assertIsNone(child)
            self.assertIn("Which child", error)

    def test_combined_real_teacher_request_answers_both_parts(self):
        with app.app.test_request_context('/'), \
                patch.object(app, '_known_subject_names', return_value=[]), \
                patch.object(app, '_known_departments', return_value=[]), \
                patch.object(app, '_teachers_with_subjects', return_value=[(7, 'Omar Khan', 'English')]), \
                patch.object(app, "handle_teacher_profile_lookup", return_value="profile") as profile, \
                patch.object(app, "handle_teacher_classes_lookup", return_value="classes") as classes:
            reply = app._combined_request_reply(
                "who is Omar Khan and which classes does he teach", "principal", 0
            )
        self.assertEqual(reply, "profile\n\nclasses")
        profile.assert_called_once_with("who is omar khan")
        classes.assert_called_once_with("classes taught by omar khan")

    def test_calendar_context_does_not_capture_private_or_subject_followups(self):
        with app.app.test_request_context("/"):
            app.session["general_context"] = {
                "topic": "exams", "day": "tuesday", "grade": "9",
                "expires_at": time.time() + 60,
            }
            self.assertEqual(app._apply_general_followup_context("what about her fees"),
                             "what about her fees")
            self.assertEqual(app._apply_general_followup_context("sorry physics"),
                             "sorry physics")
            self.assertEqual(app._apply_general_followup_context("what about monday"),
                             "school exam schedule for grade 9 on monday")

    def test_repeated_social_turns_bypass_stale_context(self):
        self.assertIn("Nova", app._conversational_reply("hello again"))
        self.assertEqual(app._conversational_reply("thanks again"), "You're welcome.")

    def test_private_record_requests_get_specific_denials(self):
        with app.app.test_request_context("/"):
            reply = app._privacy_boundary_reply(
                "show me Aanya Sharma's attendance", "student"
            )
            self.assertIn("another student's private information", reply)
            self.assertIn("login credentials", app._privacy_boundary_reply(
                "show qa_teacher login details", "principal"
            ))
            self.assertIn("private contact", app._privacy_boundary_reply(
                "Mr Omar Khan's phone number", "teacher"
            ))

    def test_public_fee_structure_is_not_treated_as_another_students_record(self):
        with app.app.test_request_context("/"):
            question = "please show the full school fee structure"
            self.assertIsNone(app._privacy_boundary_reply(question, "student"))
            self.assertIsNone(app._privacy_boundary_reply(question, "guest"))

    def test_explicit_department_schedule_is_not_replaced_by_own_department(self):
        with patch.object(app, "_known_departments", return_value=DEPARTMENTS + [(4, "English")]), \
                patch.object(app, "_hod_department_id", return_value=1), \
                patch.object(app, "query", return_value=[]):
            self.assertEqual(app.extract_department_from_question(
                "science department schedule monday"), (1, "Science"))
            self.assertEqual(app.extract_department_from_question(
                "english department schedule monday"), (4, "English"))
            self.assertEqual(
                app.handle_department_schedule_today(
                    7, "english department schedule monday", role="hod"),
                "I can only show the schedule for your own department.",
            )
            reply = app.handle_department_schedule_today(
                7, "science department schedule monday", role="vice_principal"
            )
            self.assertIn("Science Department", reply)
            self.assertNotIn("Computer Science", reply)

    def test_class_then_subject_followups_replace_one_slot_each(self):
        with app.app.test_request_context("/"):
            app.session["conversation_context"] = {
                "intent": "school_wide_subject_teacher", "role": "teacher",
                "subject": "Physics", "class": "12-A", "day": None,
                "teacher_names": ["Zara Kapoor"],
                "expires_at": time.time() + 60,
            }
            with patch.object(app, "_known_subject_names", return_value=SUBJECTS), \
                    patch.object(app, "_dispatch_to_role_handler", return_value="physics 12b") as dispatch, \
                    patch.object(app, "_remember_conversation_context"):
                self.assertEqual(app._resume_conversation_context(
                    "what about 12b", "teacher", 3), "physics 12b")
                self.assertEqual(dispatch.call_args.args[1], "who teaches Physics in 12-B")

            app.session["conversation_context"]["class"] = "12-B"
            with patch.object(app, "_known_subject_names", return_value=SUBJECTS), \
                    patch.object(app, "_dispatch_to_role_handler", return_value="chemistry 12b") as dispatch, \
                    patch.object(app, "_remember_conversation_context"):
                self.assertEqual(app._resume_conversation_context(
                    "and chemstry", "teacher", 3), "chemistry 12b")
                self.assertEqual(dispatch.call_args.args[1], "who teaches Chemistry in 12-B")

    def test_plural_pronoun_after_multiple_teachers_clarifies(self):
        with app.app.test_request_context("/"):
            app.session["conversation_context"] = {
                "intent": "school_wide_subject_teacher", "role": "vice_principal",
                "subject": "Mathematics", "class": "10-B", "day": None,
                "teacher_names": ["Ali Nair", "Rohan Hussain"],
                "expires_at": time.time() + 60,
            }
            reply = app._resume_conversation_context(
                "what subject do they teach", "vice_principal", 4
            )
            self.assertIn("Which teacher", reply)
            self.assertIn("Ali Nair", reply)

    def test_logout_clears_server_session(self):
        client = app.app.test_client()
        with client.session_transaction() as state:
            state["user_id"] = 9
            state["conversation_context"] = {"intent": "timetable"}
        response = client.post("/api/logout")
        self.assertEqual(response.status_code, 200)
        with client.session_transaction() as state:
            self.assertNotIn("user_id", state)
            self.assertNotIn("conversation_context", state)

    def test_class_teacher_choice_keeps_the_original_class(self):
        client = app.app.test_client()
        with client.session_transaction() as state:
            state.update(user_id=4, role="vice_principal", linked_id=3)
            state["pending_clarification"] = {
                "intent": "class_teacher_choice", "role": "vice_principal",
                "class": "10-A", "original_message": "who handles 10a",
                "expires_at": time.time() + 60,
            }
        with patch.object(app, "_chatbot_enabled", return_value=True), \
                patch.object(app, "handle_class_teacher", return_value="10-A teacher") as handler, \
                patch.object(app, "_remember_conversation_context"):
            response = client.post("/api/chat", json={"message": "class teacher"})
        self.assertEqual(response.get_json()["reply"], "10-A teacher")
        handler.assert_called_once_with("10-A")

    def test_department_and_general_topic_followups_replace_old_context(self):
        with app.app.test_request_context("/"):
            app.session["conversation_context"] = {
                "intent": "department_staff", "role": "hod",
                "subject": None, "class": None, "day": None,
                "department": "Mathematics", "teacher_names": [],
                "expires_at": time.time() + 60,
            }
            with patch.object(app, "_known_departments", return_value=DEPARTMENTS), \
                    patch.object(app, "handle_department_staff", return_value="cs staff") as handler, \
                    patch.object(app, "_remember_conversation_context"):
                self.assertEqual(app._resume_conversation_context(
                    "what about computer science", "hod", 3), "cs staff")
                handler.assert_called_once_with("Computer Science")

            app.session["general_context"] = {
                "topic": "events", "day": "monday", "grade": None,
                "expires_at": time.time() + 60,
            }
            self.assertEqual(app._apply_general_followup_context("what about tuesday"),
                             "school events on tuesday")
            self.assertEqual(app._apply_general_followup_context("and exams for grade 8"),
                             "school exam schedule for grade 8 on tuesday")

    def test_new_topic_clears_old_teacher_antecedent(self):
        with app.app.test_request_context("/"):
            app.session["conversation_context"] = {
                "intent": "class_teacher", "role": "student",
                "subject": None, "class": "10-A", "day": None,
                "teacher_names": ["Vivaan Mehta"],
                "expires_at": time.time() + 60,
            }
            self.assertIsNone(app._resume_conversation_context(
                "tell me about school fees", "student", 1
            ))
            self.assertNotIn("conversation_context", app.session)

    def test_calendar_gap_and_bare_class_followup_are_targeted(self):
        with app.app.test_request_context("/"):
            with patch.object(app, "search_almanac", return_value=""), \
                    patch.object(app, "search_notice_context", return_value=""):
                self.assertEqual(
                    app._calendar_information_gap_reply(
                        "school events on monday", "principal"),
                    "I couldn't find a school event listed for Monday. "
                    "Check the latest school notice or contact the school office.",
                )
                self.assertEqual(
                    app._calendar_information_gap_reply(
                        "school exam schedule for grade 8 on tuesday", "principal"),
                    "I couldn't find a Grade 8 exam schedule for Tuesday. "
                    "Check the latest exam circular or contact the school office.",
                )
            with patch.object(
                    app, "search_almanac",
                    return_value="ADMISSIONS / Entrance examination dates\nApplications open in January",
                 ), patch.object(app, "search_notice_context", return_value=""):
                self.assertEqual(
                    app._calendar_information_gap_reply(
                        "school exam schedule for grade 8 on tuesday", "principal"),
                    "I couldn't find a Grade 8 exam schedule for Tuesday. "
                    "Check the latest exam circular or contact the school office.",
                )
            self.assertTrue(app._BARE_CLASS_FOLLOWUP_RE.fullmatch("what about 10-a"))


if __name__ == "__main__":
    unittest.main()
