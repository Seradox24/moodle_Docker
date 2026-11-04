# Moodle 5.3.0: instalación y operación en Linux

## Alcance de la línea 5.3 LTS

El instalador 1.1.1 fija Moodle 5.3.0 y PostgreSQL 17.11. Requiere PHP 8.3
o superior compatible y PostgreSQL 17 como mínimo. Esta guía instala en un
proyecto nuevo con volúmenes vacíos; no migra instalaciones 5.2.4/PostgreSQL 16.
No iniciar PostgreSQL 17 sobre el volumen de PostgreSQL 16. No sustituir el
código de una instalación existente: `code-init` comprueba su revisión y rechaza
una release diferente. Preparar cualquier migración como operación independiente
con respaldo y retorno. La restauración incluida solo acepta la misma release.

Para reproducir la base anterior, usar el tag
`moodle-5.2.4-launcher-1.0.7` o la rama `moodle-5.2.4` del mismo repositorio.
Para una instalación reproducible de 5.3, seleccionar el tag
`moodle-5.3.0-launcher-1.1.1` cuando esté publicado; `main` puede avanzar.
La 1.1.1 conserva Moodle 5.3.0 y solo cambia `config/config.php`: oculta las
tarjetas promocionales de Administración > Notificaciones (Marketplace,
MoodleCloud, proveedores de servicios y encuesta), que Moodle 5.3 solo permite
desactivar en `config.php`.

Este repositorio contiene el despliegue Docker de Moodle en Linux. `main` contiene la
base validada para pseudoproducción. Las versiones de Moodle y de las imágenes
están fijadas en `releases/release.env`. Los registros de pruebas y
el estado de preparación para producción se conservan en documentación
operativa separada. La URL de su repositorio se añadirá cuando esté disponible.
Las rutas de despliegue, dominios y correos mostrados son ejemplos; adaptarlos
al entorno de instalación. `127.0.0.1:18080` es el destino local del proxy
definido por Compose.
El `.env`, las credenciales SMTP y el procedimiento privado para aplicar los
ajustes tras reinstalar se guardan fuera de Git en una ruta local, con permisos
restringidos para los archivos privados.

## Archivos necesarios

- `compose.yaml`: servicios web, PHP, cron, PostgreSQL y Redis.
- `Dockerfile`, `docker/` y `config/`: imágenes y configuración de Moodle.
- `releases/release.env`: versiones y referencias fijadas de las imágenes.
- `.env.example`: plantilla única, sin contraseñas reales.
- `scripts/`: instalación, validación, operación y copia de seguridad.

No subir archivos `.env`, respaldos, bases de datos ni `moodledata` a Git.
Los tres volúmenes de Compose guardan la base, los archivos de Moodle y el
código compartido; `docker compose down -v` los elimina.

## Producción en Ubuntu

Requisitos: Docker Engine con el plugin Compose, Git, curl, conexión de salida para
construir las imágenes, Nginx del host y una URL definitiva para Moodle.
Instalar Docker siguiendo su [guía oficial para Ubuntu](https://docs.docker.com/engine/install/ubuntu/).
Comprobar que el puerto local 18080 esté libre. Clonar el repositorio en una
carpeta vacía; los comandos usan `/srv/plataforma/moodle` como ejemplo:

```bash
git clone --branch main --single-branch https://github.com/Seradox24/moodle_Docker.git /srv/plataforma/moodle
cd /srv/plataforma/moodle
git rev-parse HEAD
cp .env.example .env
chmod 600 .env
nano .env
```

Completar los campos obligatorios y revisar las opciones de instalación de `.env`:

- `POSTGRES_PASSWORD` y `MOODLE_ADMIN_PASSWORD`: contraseñas fuertes y distintas.
- `MOODLE_SITE_FULLNAME`, `MOODLE_SITE_SHORTNAME` y `MOODLE_ADMIN_EMAIL`.
- `MOODLE_WWWROOT`: URL pública definitiva asignada por el Nginx central, por ejemplo `https://moodle.example.com`.

Compose publica en loopback mediante `MOODLE_HTTP_BIND=127.0.0.1` y el puerto
`MOODLE_HTTP_PORT` del perfil. Seleccionar `COMPOSE_PROJECT_NAME` antes de instalar
y configurar `TZ` con una zona IANA real. Los valores de proxy y Redis tienen
valores predeterminados documentados para esta topología. `scripts/prepare-env.sh` genera únicamente perfiles de prueba;
el `.env` de producción se crea y completa manualmente.

La URL pública debe resolver hacia el servidor; `localhost:18080` es solo el
destino interno del Nginx central, nunca la URL que ven los usuarios.
Preparar DNS y certificado para el dominio elegido antes de publicar Moodle.
La rama `main` contiene la base validada; registrar y comprobar el commit
seleccionado antes de instalar y revisar los pendientes documentados. El archivo `.env` se crea y edita en el
servidor. No copiar el perfil local de pruebas al sitio público.

Validar e instalar:

```bash
sh ./scripts/preflight.sh
sh ./scripts/install.sh
```

El instalador construye las imágenes, inicia PostgreSQL y Redis, prepara el
código compartido, instala la base con la CLI de Moodle e inicia web y cron.
Si `install.sh` termina correctamente, Moodle ya queda instalado en el servidor
y el servicio web escucha en `127.0.0.1:18080`. El siguiente paso es conectar
el dominio al reverse proxy Nginx del host, según la
[referencia de publicación HTTPS](#publicación-https-y-comprobaciones).
La comprobación HTTP se realiza después de activar ese proxy.

Después de instalar y publicar por HTTPS, revisar los ajustes desde Administración.
El usuario administrador inicial lo define `MOODLE_ADMIN_USER` (predeterminado `admin`). En Moodle 5.3.0,
el acceso de la app móvil se activa por defecto si el sitio usa HTTPS. Para
mantenerlo desactivado, desmarcar «Habilitar servicios web para dispositivos móviles»
en Características avanzadas. Esto conserva el acceso desde navegadores móviles.
Configurar el servidor SMTP, el tipo de seguridad, la autenticación, el usuario,
la contraseña y el remitente en «Configuración de correo saliente». Guardar esas
credenciales por separado del repositorio; los campos iniciales de `.env.example`
siguen siendo los datos de instalación.

Los datos del sitio y del administrador son valores iniciales: cambiar esos
campos en `.env` no actualiza por sí solo la cuenta ni el sitio ya instalado.
Gestionar esos cambios desde Moodle y actualizar por separado la documentación
privada de reinstalación.

## Publicación HTTPS y comprobaciones

La conexión se configura en el **Nginx del servidor**, en el bloque HTTPS
`server` del dominio de Moodle y su `location /`, con destino
`proxy_pass http://127.0.0.1:18080`. En Ubuntu, este bloque suele estar en
`/etc/nginx/sites-available/` y habilitado desde `/etc/nginx/sites-enabled/`;
su configuración se administra fuera del repositorio.

Usar el dominio definido en `MOODLE_WWWROOT`, certificado válido, encabezados
`Host` y `X-Forwarded-Proto https`, redirección HTTP a HTTPS y límite de petición
`client_max_body_size 300M` acorde con `MOODLE_MAX_REQUEST_MB`.
Validar con `nginx -t` antes de recargar. Mantener el puerto 18080 ligado a
localhost y conservar los bloques de otros sitios. El procedimiento de DNS,
certificados y configuración del proxy pertenece a la documentación del servidor.

Desde la raíz del clon, con la URL pública accesible:

```bash
sh ./scripts/status.sh
sh ./scripts/release-info.sh
sh ./scripts/smoke-test.sh
docker compose -f compose.yaml --env-file .env --env-file releases/release.env exec -T --user www-data app php /var/www/moodle/public/admin/cli/checks.php
```

La prueba de humo verifica la base, Redis, el runtime, los permisos del código,
el acceso HTTP y las rutas internas protegidas. Revisar también los informes
de seguridad desde Administración.

Probar el acceso HTTPS real, el inicio de sesión, la creación y descarga de
contenido con una cuenta de usuario final, el correo saliente y la recuperación
de contraseña. El código de solo lectura protege los archivos de la aplicación;
PostgreSQL y `moodledata` siguen permitiendo crear cursos, usuarios y contenido.
Antes de recibir usuarios, disponer de copias externas al servidor y comprobar la
restauración conjunta de base, `moodledata` y código con plugins. El estado de
estas comprobaciones debe registrarse en la documentación operativa externa.

## Arranque de una instalación existente

```bash
sh ./scripts/start.sh
sh ./scripts/status.sh
sh ./scripts/smoke-test.sh
```

`start.sh` inicia los servicios sin reinstalar la base. `install.sh` se usa
únicamente para un proyecto nuevo. Conservar el nombre del proyecto Compose,
los tres volúmenes y la configuración de base de datos de una instalación
existente. Cambiar la contraseña de PostgreSQL solo en `.env` no cambia la
contraseña del rol almacenada en la base.

## Actualizar el instalador sin cambiar Moodle

Aplica a releases que conservan `MOODLE_VERSION` y `MOODLE_GIT_REF`, como
1.1.0 → 1.1.1. `code-init` acepta el volumen `moodle-code` existente porque la
revisión de Moodle no cambia; si cambia, es una actualización de Moodle y requiere
su propio procedimiento. Desde el clon, con el perfil de la instalación:

```bash
sh ./scripts/backup.sh --env-file /ruta/privada/instancia.env /ruta/respaldos/antes-de-la-release
git fetch --tags origin
git checkout --detach moodle-5.3.0-launcher-1.1.1
sh ./scripts/compose.sh --env-file /ruta/privada/instancia.env build app web
sh ./scripts/start.sh --env-file /ruta/privada/instancia.env
sh ./scripts/compose.sh --env-file /ruta/privada/instancia.env exec -T --user www-data app php /usr/local/bin/check-runtime.php
sh ./scripts/compose.sh --env-file /ruta/privada/instancia.env exec -T --user www-data app php /var/www/moodle/admin/cli/purge_caches.php
sh ./scripts/smoke-test.sh --env-file /ruta/privada/instancia.env
```

Las imágenes de la release anterior permanecen en el servidor. Para volver,
seleccionar el tag anterior y repetir `start.sh`. Los respaldos tomados con una
release se restauran con esa misma release.

## Respaldo y recuperación

En una ventana de mantenimiento, con los servicios activos:

```bash
sh ./scripts/backup.sh
```

El script detiene temporalmente `web`, `app` y `cron`, respalda PostgreSQL,
`moodledata` y `moodle-code`, y vuelve a iniciar los servicios. Conserva los
plugins y temas instalados junto con el código. El destino predeterminado es
`backups/FECHA_HORA`; comprobar su integridad sustituyendo ese nombre por
la carpeta indicada al terminar:

```bash
(cd backups/FECHA_HORA && sha256sum -c SHA256SUMS)
sh ./scripts/status.sh
sh ./scripts/smoke-test.sh
```

Guardar una copia fuera del servidor y conservar el `.env` privado por separado:
el respaldo no lo incluye. Este procedimiento es manual; la frecuencia y
retención se definen en la documentación operativa externa.

La recuperación debe usar un proyecto Compose aislado y los tres componentes
del mismo respaldo: base, `moodledata` y `moodle-code`, junto con su revisión e
imágenes correspondientes. No restaurar sobre los volúmenes del sitio activo.
El procedimiento detallado y la evidencia del ensayo se conservan en la
documentación operativa externa. Validar la base, los archivos y el acceso antes
de cambiar el proxy hacia el sitio recuperado.


## Integraciones de identidad y eventos

[Keycloak OIDC Stack](https://github.com/Seradox24/keycloak-oidc-stack) configura
el proveedor de identidad. El cliente confidencial `moodle` admite el retorno
exacto `/auth/oidc/` del plugin de autenticación.

[Moodle Logstore xAPI OIDC](https://github.com/Seradox24/moodle-logstore-xapi-oidc)
envía eventos a un LRS con identidad OIDC. Su componente en Moodle es
`logstore_xapi`. Ambas integraciones requieren configuración por instalación.

## Instalar plugins desde Administración

Para el paquete versionado, preferir el [procedimiento offline](plugins/README.md):
`python3 scripts/install-plugins.py --env-file /ruta/privada/sitio.env --set supported`.
Requiere ensayo aislado y respaldo previo. Las instalaciones nuevas lo ejecutan
al finalizar; `install.sh --plugins none` permite instalar solo el núcleo. La
escritura se limita a un contenedor efímero durante mantenimiento, sin publicar
un servicio web con escritura. Las actualizaciones son explícitas con `--upgrade`,
después de actualizar y revisar el catálogo; no ocurren por ejecutar `git pull`.
El procedimiento web siguiente se conserva para otros plugins revisados.

En operación normal `app`, `web` y `cron` leen `moodle-code` sin permiso de
escritura. Para instalar un plugin compatible con Moodle 5.3.0, probarlo primero
en desarrollo y respaldar base, `moodledata` y código. Abrir la ventana solo el
tiempo necesario. Desde la raíz del clon, con el `.env` seleccionado:

```bash
docker compose -f compose.yaml -f compose.plugins.yaml --env-file .env --env-file releases/release.env up -d --no-deps --force-recreate app
docker compose -f compose.yaml -f compose.plugins.yaml --env-file .env --env-file releases/release.env exec -T --user www-data app php /usr/local/bin/check-runtime.php
```

Instalar el ZIP desde Administración > Plugins > Instalar plugins, confirmar
las pantallas de actualización y comprobar el sitio. Cerrar la ventana incluso
si falla la instalación:

```bash
docker compose -f compose.yaml --env-file .env --env-file releases/release.env up -d --no-deps --force-recreate app
docker compose -f compose.yaml --env-file .env --env-file releases/release.env exec -T --user www-data app php /usr/local/bin/check-runtime.php
```

`--no-deps` evita tocar los demás servicios. Esperar a que `app` esté saludable
antes de ejecutar la comprobación de runtime o acceder al instalador de plugins.
Consultar su estado incluyendo ambos archivos de entorno:

```bash
docker compose -f compose.yaml --env-file .env --env-file releases/release.env ps
```

Los plugins persisten en el volumen `moodle-code`.
No ejecutar `docker compose up` con `compose.plugins.yaml` como configuración
habitual.

## Perfil independiente de instalación

Todos los scripts aceptan `--env-file /ruta/privada/instancia.env`. Las rutas
relativas se resuelven desde el repositorio, sin depender de la consola.
El cargador rechaza variables administradas exportadas en la consola para evitar
sobrescrituras ocultas. Compose carga primero el perfil elegido y después
`releases/release.env`; las versiones pertenecen a la release, no a la instalación.
Los valores reales y secretos nunca se guardan en los ejemplos ni en este repositorio.

| Opción | Consumidor y momento |
| --- | --- |
| `COMPOSE_PROJECT_NAME` | Compose al crear contenedores, redes y volúmenes. No cambiar en instalaciones existentes sin migración explícita. |
| `MOODLE_HTTP_BIND`, `MOODLE_HTTP_PORT` | Publicación Docker al crear/recrear web; bind obligatorio 127.0.0.1 detrás del proxy del host. |
| `TZ` | Contenedores web/app/cron/db y opciones timezone/log_timezone de PostgreSQL al iniciar. Predeterminado UTC; validar zona IANA instalada en el host. |
| `MOODLE_WWWROOT` | Configuración Moodle en ejecución; el virtual host y TLS del host deben coincidir. |
| `MOODLE_SITE_FULLNAME`, `MOODLE_SITE_SHORTNAME`, `MOODLE_LANG`, `MOODLE_ADMIN_USER`, `MOODLE_ADMIN_EMAIL`, `MOODLE_ADMIN_PASSWORD` | CLI de instalación inicial. Cambiar el perfil después no modifica el sitio ni cuentas existentes. |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Inicialización PostgreSQL y conexión Moodle. La rotación del rol requiere operación SQL explícita coordinada con el perfil. |

Ejemplo de respaldo externo: `sh scripts/backup.sh --env-file /ruta/privada/instancia.env /ruta/respaldos/FECHA`.
El respaldo no contiene el perfil privado. Conservarlo protegido por separado.
Los tres volúmenes siguen gestionados por Docker; no se requieren bind mounts.

El instalador 1.1.1 utiliza Moodle 5.3.0 LTS, PHP 8.3.36 y PostgreSQL 17.11,
con referencias fijadas por SHA/digest. La construcción instala las
dependencias Composer bloqueadas de Moodle (necesarias para la API REST y
OpenAPI) con `COMPOSER_IMAGE`; requiere acceso a Packagist/GitHub al construir.
Los requisitos y el alcance de
instalación limpia se detallan al inicio de esta guía y en los
[requisitos oficiales de Moodle 5.3](https://moodledev.io/general/releases/5.3).

## Respaldo periódico y ensayo de recuperación

`python3 scripts/backup-retained.py --env-file /ruta/privada/instancia.env --destination /ruta/respaldos --keep 7`
serializa ejecuciones mediante un bloqueo, comprueba los checksums y conserva
los siete respaldos completos más recientes. Un fallo conserva el directorio
`.partial`, devuelve error y no elimina respaldos previos. Ejecutarlo con umask
0077 desde un timer del host, con zona IANA y hora explícitas; revisar journal
ante fallos. Detiene brevemente app/web/cron. El almacenamiento local no
sustituye una copia externa.

`sh scripts/restore.sh --env-file /ruta/privada/recuperacion.env --backup /ruta/respaldo`
requiere un proyecto sin contenedores ni volúmenes existentes, metadata de
release coincidente e imágenes disponibles. Restaura los tres componentes sin
modificar el proyecto original. Para un ensayo, usar otro nombre Compose, otro
puerto loopback y URL local con `MOODLE_SSLPROXY=false` y
`MOODLE_REVERSEPROXY=true`; no apuntar el proxy público al ensayo.
Comprobar login y contenido antes de retirar únicamente los recursos del ensayo.
Validación estática de perfiles: `python3 tests/profiles.py` (Linux con Compose).

El Nginx del host se genera desde el perfil efectivo mediante
`python3 scripts/render-proxy.py --env-file /ruta/privada/instancia.env --acme-root /var/www/letsencrypt --certificate-dir /etc/letsencrypt/live/DOMINIO`.
Sin `--certificate-dir` genera solo HTTP/ACME. Guardar primero la salida en un
archivo temporal y comprobarla antes de instalar; validar con `nginx -t` y
recargar. El generador no instala certificados ni modifica Nginx por sí mismo.
`TZ` también genera `date.timezone` en PHP al iniciar y configura la zona del sitio Moodle en ejecución; web incluye tzdata.
