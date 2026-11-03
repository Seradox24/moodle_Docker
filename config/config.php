<?php

unset($CFG);
global $CFG;
$CFG = new stdClass();

function env_value(string $name, ?string $default = null): ?string {
    $value = getenv($name);
    return ($value === false || $value === '') ? $default : $value;
}

function env_bool(string $name, bool $default = false): bool {
    $value = env_value($name);
    if ($value === null) {
        return $default;
    }
    return filter_var($value, FILTER_VALIDATE_BOOL);
}

function env_secret(string $name, ?string $default = null): ?string {
    $file = env_value($name . '_FILE');
    if ($file !== null) {
        if (!is_readable($file)) {
            throw new RuntimeException("Secret file for {$name} is not readable: {$file}");
        }
        return rtrim((string)file_get_contents($file), "\r\n");
    }
    return env_value($name, $default);
}

$CFG->dbtype = 'pgsql';
$CFG->dblibrary = 'native';
$CFG->dbhost = env_value('MOODLE_DB_HOST', 'db');
$CFG->dbname = env_value('POSTGRES_DB', 'moodle');
$CFG->dbuser = env_value('POSTGRES_USER', 'moodle');
$CFG->dbpass = env_secret('POSTGRES_PASSWORD', '');
$CFG->prefix = env_value('MOODLE_DB_PREFIX', 'mdl_');

$CFG->dboptions = [
    'dbpersist' => false,
    'dbsocket' => false,
    'dbport' => (int)env_value('MOODLE_DB_PORT', '5432'),
];

$wwwroot = env_value('MOODLE_WWWROOT');
if ($wwwroot === null) {
    throw new RuntimeException('MOODLE_WWWROOT is required.');
}
$CFG->wwwroot = rtrim($wwwroot, '/');
$CFG->dataroot = '/var/moodledata';
$CFG->directorypermissions = 0770;

$CFG->reverseproxy = env_bool('MOODLE_REVERSEPROXY', false);
$CFG->sslproxy = env_bool('MOODLE_SSLPROXY', true);
$CFG->routerconfigured = env_bool('MOODLE_ROUTER_CONFIGURED', true);
$CFG->slasharguments = true;
$CFG->preventexecpath = true;

$CFG->disableupdateautodeploy = !env_bool('MOODLE_PLUGIN_INSTALL', false);
$CFG->timezone = env_value('TZ', 'UTC');
$CFG->debug = 0;
$CFG->debugdisplay = false;

// Moodle 5.3 only allows hiding the promotional cards on Administration >
// Notifications from config.php; keep them hidden on every installation.
$CFG->disablenotificationctas = ['marketplace', 'moodlecloud', 'partners', 'feedback'];

if (env_bool('MOODLE_REDIS_SESSIONS', true)) {
    $CFG->session_handler_class = '\core\session\redis';
    $CFG->session_redis_host = env_value('MOODLE_REDIS_HOST', 'redis');
    $CFG->session_redis_port = (int)env_value('MOODLE_REDIS_PORT', '6379');
    $CFG->session_redis_database = (int)env_value('MOODLE_REDIS_DATABASE', '0');
    $CFG->session_redis_prefix = env_value('MOODLE_REDIS_PREFIX', 'moodle_session_');
    $CFG->session_redis_acquire_lock_timeout = 120;
    $CFG->session_redis_lock_expire = 7200;
}

require_once(__DIR__ . '/lib/setup.php');
