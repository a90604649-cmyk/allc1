# Dúo Chat para Windows

Aplicación de chat visible para dos computadoras Windows, sin cuentas, nombres ni teléfonos. GitHub Actions la empaqueta como un único `DuoChat.exe`; ninguna PC donde se ejecuta necesita instalar Python.

## Descargar el ejecutable

1. Abre la pestaña **Actions** de este repositorio.
2. Abre la ejecución más reciente de **Build portable Windows EXE**.
3. Espera a que termine correctamente y descarga **DuoChat-Windows** en Artifacts.
4. Descomprime el ZIP y copia `DuoChat.exe` a la otra PC.

## Uso automático

1. Conecta ambas computadoras a la misma red Wi-Fi/LAN.
2. Abre `DuoChat.exe` en la primera PC.
3. Abre `DuoChat.exe` en la segunda PC.
4. La aplicación descubre la otra instancia y conecta el chat automáticamente; no hay botones para crear/unirse ni códigos que introducir.

Al cerrar con la X, Esc o Ctrl+Q, la aplicación notifica a la otra PC para que también se cierre. Si Windows muestra una alerta de firewall al primer uso, permite la comunicación en redes privadas. Redes de invitados, aislamiento de clientes Wi-Fi o reglas del firewall pueden impedir el descubrimiento.

## Privacidad y límites

No pide cuenta, nombre, correo ni teléfono. El historial no se guarda en disco y la ventana es visible (no se ejecuta oculta). Este prototipo solo funciona en una misma red local y **no cifra los mensajes de extremo a extremo**; no lo uses para información sensible. Está diseñado para dos PCs con Dúo Chat abierto; si hay más de dos copias en la misma red, no se garantiza qué dos se emparejarán.

El EXE se construye con GitHub Actions usando la receta de `.github/workflows/build-windows.yml`.
