<?php
declare(strict_types=1);

// Install as a mode-0600 file outside every release and outside public_html.
return [
    'db_dsn'=>'mysql:host=localhost;dbname=tenuoboe_baiamonte_erp;charset=utf8mb4',
    'db_user'=>'APP_CRUD_USER',
    'db_password'=>'APP_CRUD_PASSWORD',
    'private_dir'=>'/home/tenuoboe/apps/baiamonte-secondary/private/mobile-intake',
];
