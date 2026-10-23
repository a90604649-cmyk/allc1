# Dúo Chat para Windows

Aplicación visible para chatear entre dos computadoras Windows, sin cuentas, nombres ni teléfonos. GitHub Actions crea un único `DuoChat.exe`; las computadoras donde se ejecuta no necesitan instalar Python.

## Descargar

1. Entra en **Actions**.
2. Abre la ejecución más reciente de **Build portable Windows EXE**.
3. Cuando termine con éxito, descarga **DuoChat-Windows** en Artifacts.
4. Descomprime el ZIP y copia `DuoChat.exe` a la otra PC.

## Uso

1. Conecta ambas PC a la misma red Wi-Fi/LAN.
2. Abre `DuoChat.exe` en las dos computadoras.
3. Se buscan y conectan automáticamente, sin IP ni código.
4. Al cerrar una ventana con la **X de Windows**, se avisa a la otra PC para que también se cierre.
5. Pulsa **J** para mostrar u ocultar la consola de diagnóstico en una esquina. Ahí se registran los intentos de conexión, equipos detectados y errores de red.

Si aparece una alerta del Firewall de Windows, permite Dúo Chat en redes privadas. Las redes de invitados, el aislamiento de clientes Wi-Fi o las reglas del firewall pueden impedir que las PC se vean.

## Privacidad y límites

No pide cuenta, nombre, correo ni teléfono. El historial de mensajes no se guarda en disco y la ventana se mantiene visible (no se ejecuta oculta). Esta versión funciona solo en una misma red local y **no cifra los mensajes de extremo a extremo**; no la uses para información sensible. Está pensada para dos instancias; si hay más de dos copias ejecutándose en la misma red, el emparejamiento no está garantizado.

La compilación portátil está definida en `.github/workflows/build-windows.yml`.
