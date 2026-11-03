<?php
// Run as www-data through app stdin after installing mod_customcert.
define('CLI_SCRIPT', true);
if (!str_starts_with(getenv('COMPOSE_TEST_PROJECT') ?: '', 'release-check-')) {
    throw new RuntimeException('This fixture is restricted to disposable release-check projects.');
}
require '/var/www/moodle/config.php';
require_once($CFG->dirroot . '/user/lib.php');
require_once($CFG->dirroot . '/course/lib.php');
require_once($CFG->dirroot . '/course/modlib.php');

if (get_config('mod_customcert', 'version') != 2026100504) {
    throw new RuntimeException('Locked mod_customcert 5.3.4 is required for this test.');
}

\core\session\manager::set_user(get_admin());
$token = 'certcheck' . bin2hex(random_bytes(5));
$courseid = null;
$userid = null;
$certificateid = null;
$issueid = null;

try {
    $categoryid = $DB->get_field_sql('SELECT MIN(id) FROM {course_categories}');
    $course = create_course((object)[
        'category' => $categoryid,
        'fullname' => 'Prueba temporal de certificado',
        'shortname' => $token,
        'format' => 'topics',
        'enablecompletion' => 1,
    ]);
    $courseid = $course->id;
    $PAGE->set_course($course);
    $PAGE->set_context(context_course::instance($courseid));
    $PAGE->set_url('/course/view.php', ['id' => $courseid]);
    $PAGE->set_pagelayout('course');

    $user = (object)[
        'username' => $token,
        'password' => 'Aa1!' . bin2hex(random_bytes(16)),
        'firstname' => 'Estudiante',
        'lastname' => 'Temporal',
        'email' => $token . '@moodle.invalid',
        'auth' => 'manual',
        'confirmed' => 1,
        'mnethostid' => $CFG->mnet_localhost_id,
    ];
    $userid = user_create_user($user);
    $manual = enrol_get_plugin('manual');
    $enrolinstance = $DB->get_record('enrol', ['courseid' => $courseid, 'enrol' => 'manual'], '*', MUST_EXIST);
    $studentroleid = $DB->get_field('role', 'id', ['shortname' => 'student'], MUST_EXIST);
    $manual->enrol_user($enrolinstance, $userid, $studentroleid);

    [, , , , $data] = prepare_new_moduleinfo_data($course, 'customcert', 0);
    $data->name = 'Certificado temporal';
    $data->intro = 'Prueba funcional del plugin';
    $data->introformat = FORMAT_HTML;
    $data->deliveryoption = 'I';
    $data->emailstudents = 0;
    $data->emailteachers = 0;
    $data->emailothers = '';
    $data->completion = COMPLETION_TRACKING_MANUAL;
    $activity = add_moduleinfo($data, $course);
    $certificateid = (int)$activity->instance;
    $cm = get_coursemodule_from_instance('customcert', $certificateid, $courseid, false, MUST_EXIST);
    $certificate = $DB->get_record('customcert', ['id' => $certificateid], '*', MUST_EXIST);
    echo "Course, student enrolment and custom certificate activity created (cmid {$cm->id})\n";

    $page = $DB->get_record('customcert_pages', ['templateid' => $certificate->templateid], '*', MUST_EXIST);
    $DB->insert_record('customcert_elements', (object)[
        'pageid' => $page->id,
        'element' => 'text',
        'name' => 'Test text',
        'sequence' => 1,
        'posx' => 10,
        'posy' => 10,
        'refpoint' => 0,
        'alignment' => 'L',
        'timecreated' => time(),
        'timemodified' => time(),
        'data' => json_encode([
            'text' => 'Certificado de prueba',
            'font' => 'helvetica',
            'fontsize' => 18,
            'colour' => '#000000',
            'width' => 0,
        ]),
    ]);

    $issueid = \mod_customcert\service\certificate_issue_service::create()
        ->issue_certificate($certificateid, $userid);
    $issue = $DB->get_record('customcert_issues', ['id' => $issueid], '*', MUST_EXIST);
    if ((int)$issue->customcertid !== $certificateid || (int)$issue->userid !== $userid || !$issue->code) {
        throw new RuntimeException('Certificate issue record is incomplete.');
    }
    echo "Certificate issued with verification code\n";

    $template = \mod_customcert\template::from_record(
        (new \mod_customcert\service\template_repository())->get_by_id_or_fail((int)$certificate->templateid)
    );
    $pdf = \mod_customcert\service\pdf_generation_service::create()
        ->generate_pdf($template, false, $userid, true);
    if (!is_string($pdf) || !str_starts_with($pdf, '%PDF-') || strlen($pdf) < 1000 ||
            !str_contains(substr($pdf, -100), '%%EOF')) {
        throw new RuntimeException('Generated certificate is not a complete PDF.');
    }
    echo 'Certificate PDF generated (' . strlen($pdf) . ' bytes, SHA-256 ' . hash('sha256', $pdf) . ")\n";

    // Exercise the progress block against a real course with a tracked activity.
    $PAGE->blocks->add_block('completion_progress', 'side-pre', 0, false);
    $record = $DB->get_record('block_instances', [
        'blockname' => 'completion_progress', 'parentcontextid' => context_course::instance($courseid)->id,
    ], '*', MUST_EXIST);
    $block = block_instance('completion_progress', $record, $PAGE);
    $student = $DB->get_record('user', ['id' => $userid], '*', MUST_EXIST);
    $progress = (new \block_completion_progress\completion_progress($course))
        ->for_user($student)->for_block_instance($record);
    if (!$progress->has_visible_activities() || $progress->get_percentage() !== 0)
        throw new RuntimeException('Progress should start at zero with a visible tracked activity');
    (new completion_info($course))->update_state($cm, COMPLETION_COMPLETE, $userid);
    $progress = (new \block_completion_progress\completion_progress($course))
        ->for_user($student)->for_block_instance($record);
    if ($progress->get_percentage() !== 100)
        throw new RuntimeException('Completed tracked activity did not produce 100 percent progress');
    $content = $block->get_content();
    if (!$content || empty($content->text)) throw new RuntimeException('Progress block rendered no content');
    echo "Completion Progress block rendered and student progress changed from 0 to 100 percent\n";
} finally {
    if ($courseid !== null) {
        delete_course($courseid, false);
        if ($DB->record_exists('course', ['id' => $courseid])) {
            throw new RuntimeException('Temporary course was not removed.');
        }
        if ($certificateid !== null && $DB->record_exists('customcert', ['id' => $certificateid])) {
            throw new RuntimeException('Temporary certificate activity was not removed.');
        }
        if ($issueid !== null && $DB->record_exists('customcert_issues', ['id' => $issueid])) {
            throw new RuntimeException('Temporary certificate issue was not removed.');
        }
    }
    if ($userid !== null) {
        user_delete_user($DB->get_record('user', ['id' => $userid]));
        if (!$DB->record_exists('user', ['id' => $userid, 'deleted' => 1])) {
            throw new RuntimeException('Temporary student was not deactivated.');
        }
    }
    echo "Temporary course and student cleaned up\n";
}
