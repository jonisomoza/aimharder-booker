# book.py
import os, time
from datetime import date
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from pathlib import Path

ARTIFACTS_DIR = Path("artifacts")
ARTIFACTS_DIR.mkdir(exist_ok=True)

AIM_URL_LOGIN = "https://www.aimharder.com/login"   # ajustar si es distinto
AIM_URL_SCHEDULE = "https://www.aimharder.com/schedule"  # ajustar a la URL real de tu calendario/reservation

def save_debug_screenshot(tag):
    # intentamos guardar cualquier screenshot que falte
    p = ARTIFACTS_DIR / f"screenshot_{tag}.png"
    # si hay un browser/page activo lo capturaría; pero como fallback, creamos un archivo vacío
    p.write_text("debug") 

def try_book_for_date(target_date: date, storage_state_path: str = None) -> bool:
    """
    Intenta reservar la clase de 19:00 en target_date.
    Devuelve True si parece éxito, False si falla.
    storage_state_path: ruta al archivo storage_state.json (o None)
    """
    email = os.getenv("AIMHARDER_EMAIL")
    pwd = os.getenv("AIMHARDER_PASS")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)  # cambia a False para debug local
        context_args = {}
        if storage_state_path and os.path.exists(storage_state_path):
            context_args["storage_state"] = storage_state_path

        context = browser.new_context(**context_args)
        page = context.new_page()
        try:
            # si no hay storage_state, hacemos login
            if not context_args.get("storage_state"):
                page.goto(AIM_URL_LOGIN)
                page.wait_for_load_state("networkidle")
                # Ajusta los selectores de los inputs según la página real
                page.fill('input[type="email"]', email)
                page.fill('input[type="password"]', pwd)
                page.click('button[type="submit"]')
                page.wait_for_load_state("networkidle")
                # guardamos el estado para posibles usos posteriores (solo si Actions permite escribirlo)
                try:
                    context.storage_state(path="/tmp/storage_state.json")
                except Exception:
                    pass

            # navegar a la página de calendario para la fecha objetivo
            # Muchas webs aceptan query param ?date=YYYY-MM-DD; ajusta según sea el caso
            target_str = target_date.isoformat()
            schedule_url = f"{AIM_URL_SCHEDULE}?date={target_str}"
            page.goto(schedule_url)
            page.wait_for_load_state("networkidle")

            # BUSCAR la clase de 19:00: aquí hay que adaptar a la estructura de AimHarder.
            # Ejemplo genérico: buscar elemento que contenga "19:00" y dentro un botón "Reservar" / "Book"
            # Primero buscamos por texto "19:00"
            try:
                # localizador por texto (puede haber varios; elegimos el primero que tenga botón book)
                cards = page.locator("text=19:00")
                count = cards.count()
                if count == 0:
                    print("No se encontró '19:00' en la página.")
                    page.screenshot(path=str(ARTIFACTS_DIR / f"no_19_{target_str}.png"))
                    return False

                # iterar sobre coincidencias y buscar botón reservar dentro del contenedor padre
                for i in range(count):
                    el = cards.nth(i)
                    # subimos hasta un ancestro con botón (depende de la estructura)
                    # intentamos buscar un botón 'Reservar' o 'Book' cerca
                    try:
                        # mirar en el contenedor más próximo
                        box = el.locator("..")  # puede que necesites ajustar
                        btn = box.locator("button:has-text('Reservar')").first
                        if btn.count() == 0:
                            btn = box.locator("button:has-text('Book')").first
                        if btn.count() > 0:
                            btn.click()
                            page.wait_for_timeout(1500)
                            # si hay confirm modal:
                            try:
                                conf = page.locator("button:has-text('Confirmar')").first
                                if conf.count() > 0:
                                    conf.click()
                                    page.wait_for_timeout(1000)
                            except Exception:
                                pass
                            # verificar éxito:
                            if page.locator("text=Reserva confirmada").count() > 0 or page.locator("text=Booked").count() > 0:
                                page.screenshot(path=str(ARTIFACTS_DIR / f"success_{target_str}.png"))
                                return True
                            else:
                                page.screenshot(path=str(ARTIFACTS_DIR / f"after_click_{target_str}.png"))
                                # tal vez hay mensaje de error (plazas agotadas)
                                return False
                    except PWTimeout:
                        continue

                # si llegamos aquí no se hizo click
                page.screenshot(path=str(ARTIFACTS_DIR / f"no_button_{target_str}.png"))
                return False

            except Exception as e:
                print("Error buscando clase:", e)
                page.screenshot(path=str(ARTIFACTS_DIR / f"error_search_{target_str}.png"))
                return False

        finally:
            try:
                context.close()
                browser.close()
            except:
                pass
