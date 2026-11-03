# Plugins bloqueados para Moodle 5.3.0

El paquete de plugins tiene ciclo propio (`bundle_version` en `catalog.json`).
Los dos ZIP se conservan completos y se fijan por SHA-256. El catálogo registra
su versión, soporte declarado y origen. La instalación de los plugins es offline.

| Plugin | Versión | Soporte declarado |
| --- | --- | --- |
| block_completion_progress | 2026101200 | 4.5–5.3 |
| mod_certstudio | 1.0.1 / 2026100901 | 4.5–5.3 |

## Instalar en Linux

Una instalación nueva con `sh scripts/install.sh --env-file /ruta/privada/sitio.env`
instala `supported` al finalizar. Para instalar solamente Moodle, añadir
`--plugins none`. Python 3 y `flock` de su biblioteca estándar son necesarios.
El perfil privado debe tener permisos 0600. Se conserva el cargador de entorno
existente: perfil explícito, después `releases/release.env`, sin variables
administradas exportadas en la consola. Las rutas relativas parten del componente.

En un sitio existente: probar primero en una instancia aislada y crear un respaldo
consistente completo de base, moodledata y código. Coordinar el timer de respaldo
para que no coincida con la ventana; el bloqueo de plugins serializa únicamente
las ejecuciones de esta herramienta para el mismo perfil/proyecto.

```sh
python3 scripts/install-plugins.py --verify-only
python3 scripts/install-plugins.py --env-file /ruta/privada/sitio.env --set supported
```

La herramienta verifica SHA-256, identidad/versión, dependencias y rutas de los
ZIP antes de tocar servicios. Rechaza downgrade de base, colisiones con plugins
no gestionados, modificaciones locales y perfiles con permisos abiertos. Activa
mantenimiento; detiene web, PHP y cron; usa un contenedor efímero con escritura
solo en el volumen de código; ejecuta el upgrade nativo como www-data y purga
cachés. Al terminar vuelve al Compose habitual, con el código de solo lectura.
No abre una ventana de escritura del servicio web. Los ZIP no se sirven por HTTP.

Ante un fallo conserva los datos, web/cron detenidos y mantenimiento activo.
No revierte migraciones sustituyendo solo archivos. Registrar el error sin
publicar salidas sensibles, recuperar el respaldo completo en otro proyecto
según el runbook y comprobarlo antes de cambiar el proxy. Si no comenzó ninguna
migración, revisar la causa y el estado de mantenimiento antes de reintentar.

## Actualizar mediante Git

1. Seleccionar una release oficial compatible y revisar avisos de seguridad.
2. Sustituir únicamente su ZIP en `archives/`; actualizar versión, SHA-256,
   commit, URL inmutable, soporte y dependencias en `catalog.json`. No seguir
   `main`, `latest` ni descargar automáticamente al arrancar.
3. Ejecutar `python3 tests/plugin-bundle.py`, `python3 tests/profiles.py`, la
   instalación limpia, pruebas funcionales y respaldo/restauración aislados.
   Actualizar documentación y enviar un PR. Mantener licencias originales.
4. Tras revisar/integrar, transferir la revisión exacta a cada servidor, respaldar
   y ejecutar `install-plugins.py --env-file ... --set supported --upgrade`.
   El marcador privado al volumen `.stt-plugin.json` registra los archivos de
   origen y permite rechazar cambios locales antes de reemplazar el directorio.

Actualizar el repositorio no cambia un sitio ni rota cuentas por sí mismo. Las
versiones iguales se verifican; una versión mayor necesita `--upgrade`. Retirar
un plugin del catálogo no lo desinstala: la desinstalación de Moodle elimina
datos y requiere un procedimiento independiente autorizado.
