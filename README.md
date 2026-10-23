# Dúo Chat para Windows

Aplicación de chat visible entre dos computadoras Windows, sin cuentas, nombres ni teléfonos. Se empaqueta como un único `DuoChat.exe`; la otra computadora no necesita instalar Python.

## Descargar el ejecutable

1. Abre la pestaña **Actions** del repositorio.
2. Abre la ejecución más reciente de **Build portable Windows EXE**.
3. Descarga el artefacto **DuoChat-Windows** y descomprímelo para obtener `DuoChat.exe`.
4. Copia `DuoChat.exe` a la segunda computadora.

## Uso

Ambas computadoras necesitan estar en la misma red Wi-Fi/LAN. En una PC elige **Crear conversación** y comparte la IP local y el código de unión. En la otra elige **Unirme a una conversación** y escribe esos datos. La X, Esc o Ctrl+Q cierra la aplicación y notifica al otro extremo.

## Privacidad y límites

No pide cuenta, usuario, correo ni teléfono. La conversación no se guarda en el historial local, pero este prototipo **no cifra el tráfico de extremo a extremo** y solo funciona en la misma red local; no uses mensajes sensibles. La app no se ejecuta oculta: la ventana permanece visible.

El ejecutable se construye con GitHub Actions en una máquina Windows. El flujo está en `.github/workflows/build-windows.yml`.