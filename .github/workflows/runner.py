# runner.py
from datetime import date
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os, sys
from book import try_book_for_date

TZ = ZoneInfo("Europe/Madrid")

def is_local_19():
    now = datetime.now(TZ)
    # permitimos una ventana de 15 minutos: 19:00 a 19:14 para evitar sincronización exacta
    return now.hour == 19 and now.minute < 15

def get_target_date():
    now = datetime.now(TZ)
    return (now + timedelta(days=3)).date()

def is_weekday(d):
    return d.weekday() < 5

if __name__ == "__main__":
    if not is_local_19():
        print("No es la hora local (19:00 Madrid). Saliendo.")
        sys.exit(0)

    target = get_target_date()
    print("Target date:", target.isoformat())

    if not is_weekday(target):
        print("Target date es fin de semana. Saliendo.")
        sys.exit(0)

    # Para pruebas locales: fuerza usar el storage_state.json en la carpeta del proyecto
    storage_state_path = "storage_state.json"
    print("DEBUG: looking for storage_state at:", storage_state_path, "exists=", os.path.exists(storage_state_path))

    try:
        success = try_book_for_date(target, storage_state_path=storage_state_path)
        if success:
            print("Reserva realizada con éxito para", target.isoformat())
        else:
            print("La reserva NO fue confirmada. Revisa screenshots/artifacts.")
    except Exception as e:
        print("Error en el proceso de booking:", e)
        # si hay función para guardar screenshot/HTML para debug, llamarla
        try:
            save_debug_screenshot("error")
        except Exception:
            pass
        raise
