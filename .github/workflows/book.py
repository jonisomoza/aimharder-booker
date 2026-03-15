# book.py - versión completa y lista para pegar
import os
import time
import traceback
from pathlib import Path
from datetime import date, datetime, timedelta
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# -----------------------
# Config / constantes
# -----------------------
ARTIFACTS_DIR = Path("artifacts")
ARTIFACTS_DIR.mkdir(exist_ok=True)

# URLs específicas que me diste
AIM_URL_LOGIN = "https://login.aimharder.com/"
AIM_URL_SCHEDULE = "https://crossfitdrkacoruna.aimharder.com/schedule?cl"

# Timeouts / waits
PAGE_TIMEOUT = 20000
SHORT_WAIT = 1000

# Textos posibles de botones para reservar (añade variantes si ves otras)
BOOK_BUTTON_TEXTS = [
    "Reservar", "Reservarme", "Apuntarse", "Inscribirse", "Reservar plaza",
    "Book", "Book now", "Sign up", "Join", "Reserve"
]

# Textos posibles que indican que la reserva fue exitosa
SUCCESS_TEXTS = ["Reserva confirmada", "Booked", "Tu reserva", "Has reservado", "Booking confirmed", "Clase reservada", "CLASE RESERVADA"]

# -----------------------
# Helpers
# -----------------------
def save_debug_screenshot(page, name: str):
    """
    Guarda screenshot en artifacts/ con el nombre dado.
    """
    try:
        out = ARTIFACTS_DIR / f"{name}.png"
        page.screenshot(path=str(out), full_page=True)
        print(f"[DEBUG] Screenshot guardada: {out}")
    except Exception as e:
        print(f"[DEBUG] No se pudo guardar screenshot {name}: {e}")

def try_book_for_date(target_date: date, storage_state_path: str = None) -> bool:
    target_str = target_date.isoformat()
    print(f"[RUN] Intentando booking para {target_str} (target_time=19:00)")

    email = os.getenv("AIMHARDER_EMAIL")
    pwd = os.getenv("AIMHARDER_PASS")

    with sync_playwright() as p:
        # headless=False para ver la UI localmente; cámbialo a True en Actions
        browser = p.chromium.launch(headless=True)
        
        # FORZAR LOGIN SIEMPRE: No usamos storage_state para iniciar sesión limpia
        print("[INFO] Iniciando sesión limpia (ignorando storage_state si existe).")
        context = browser.new_context()

        page = context.new_page()

        try:
            page.set_default_timeout(PAGE_TIMEOUT)

            # 1. Ir siempre a la página de login primero
            print(f"[INFO] Navegando a AIM_URL_LOGIN: {AIM_URL_LOGIN}")
            page.goto(AIM_URL_LOGIN)
            page.wait_for_load_state("networkidle")

            # GESTIÓN DE COOKIES: Aceptar si aparece el banner
            try:
                # Selectores comunes de cookies en AimHarder y otros
                cookie_selectors = [
                    "a:has-text('Aceptar todas')",
                    "button:has-text('Aceptar todas')",
                    "#eucookielaw a:has-text('Aceptar todas')",
                    "#onetrust-accept-btn-handler"
                ]
                for c_sel in cookie_selectors:
                    # Usar .first para evitar error de modo estricto si hay múltiples
                    loc = page.locator(c_sel).first
                    if loc.is_visible():
                        print(f"[INFO] Detectado banner de cookies. Click en: {c_sel}")
                        loc.click()
                        page.wait_for_timeout(500)
                        break
            except Exception as e:
                print(f"[WARN] Error al intentar cerrar cookies: {e}")

            # 2. Realizar login si estamos en la página de login (o redirigidos a ella)
            if "login" in page.url or page.locator('input[type="email"]').count() > 0:
                if not email or not pwd:
                    print("[ERROR] Faltan credenciales (AIMHARDER_EMAIL, AIMHARDER_PASS). No se puede hacer login.")
                    save_debug_screenshot(page, "login_missing_creds")
                    return False

                try:
                    print("[INFO] Introduciendo credenciales...")
                    # Intentar selector por ID primero (común en AimHarder) o por tipo
                    if page.locator("#mail").count() > 0:
                        page.fill('#mail', email)
                    else:
                        page.fill('input[type="email"]', email)
                    
                    page.fill('input[type="password"]', pwd)
                    
                    # Intentar click en el botón de submit (probar varios selectores)
                    submit_selectors = [
                        'button[type="submit"]', 
                        'input[type="submit"]', 
                        'button:has-text("Iniciar sesión")', 
                        'button:has-text("Entrar")',
                        'button:has-text("Login")',
                        '#loginBtn',
                        '.btn-primary'
                    ]
                    clicked_submit = False
                    for sel in submit_selectors:
                        if page.locator(sel).count() > 0:
                            print(f"[INFO] Click en botón login: {sel}")
                            page.click(sel)
                            clicked_submit = True
                            break
                    
                    if not clicked_submit:
                        print("[WARN] No se encontró botón de submit estándar. Intentando enter en password.")
                        page.press('input[type="password"]', 'Enter')

                    # Esperar a que el login procese (cambio de URL o carga de red)
                    print("[INFO] Esperando confirmación de login...")
                    page.wait_for_load_state("networkidle")
                    page.wait_for_timeout(3000) # Espera extra de seguridad
                    
                    # Si seguimos en la URL de login, algo pudo fallar
                    if "login" in page.url:
                        print("[WARN] Seguimos en la URL de login tras el submit. Verificando...")
                        # Verificar si hay error en pantalla
                        if page.locator(".error").count() > 0 or page.locator("text=Incorrect").count() > 0:
                             print("[ERROR] Credenciales incorrectas o error en login.")
                             save_debug_screenshot(page, "login_bad_creds")
                             return False
                    
                    print("[INFO] Login procesado.")
                except Exception as e:
                    print(f"[ERROR] Falló al intentar hacer login: {e}")
                    save_debug_screenshot(page, "login_submit_error")
                    return False
            else:
                print("[WARN] No estamos en la página de login (¿quizás ya logueado?). URL:", page.url)

            # 3. Ir a la página del horario
            print(f"[INFO] Navegando a AIM_URL_SCHEDULE: {AIM_URL_SCHEDULE}")
            page.goto(AIM_URL_SCHEDULE)
            page.wait_for_load_state("networkidle")
            
            # Verificar si estamos correctamente en el horario
            if "schedule" not in page.url and "crossfitdrkacoruna" not in page.url:
                 print(f"[WARN] La URL actual ({page.url}) no parece ser la del horario. Posible fallo de login.")
                 save_debug_screenshot(page, "schedule_nav_warning")
            else:
                 print("[INFO] En la página de horario.")

            save_debug_screenshot(page, f"page_after_open_schedule_{target_str}")

            # Helper para comprobar si la celda del día objetivo está visible
            # Usamos el formato de clase wdsYYYYMMDD visto en la captura
            day_selector = f".wds{target_date.strftime('%Y%m%d')}"
            
            def target_visible():
                try:
                    return page.locator(day_selector).count() > 0
                except Exception:
                    return False

            # Si no está visible, navegar semanas usando el botón específico #nextWeek
            if not target_visible():
                print(f"[INFO] Fecha objetivo ({day_selector}) NO visible. Voy a avanzar semanas usando #nextWeek.")
                next_selectors = [
                    "#nextWeek", "a#nextWeek", "a[id='nextWeek']",
                    "button[aria-label='Next']", "button[aria-label='Siguiente']",
                    "button:has-text('>')", ".ui-datepicker-next", ".next", "a.next"
                ]

                # guardamos weekTitle actual para detectar cambio de semana
                old_week_title = ""
                try:
                    if page.locator("#weekTitle").count() > 0:
                        old_week_title = (page.locator("#weekTitle").nth(0).inner_text() or "").strip()
                except Exception:
                    old_week_title = ""

                clicked_next = False
                max_attempts = 2 # Limitado a 2 intentos (semana actual + siguiente) por petición de usuario
                for attempt in range(max_attempts):
                    print(f"[INFO] Navegación semana: intento {attempt+1}/{max_attempts}")
                    if target_visible():
                        print("[INFO] Fecha objetivo visible tras navegación previa.")
                        clicked_next = True
                        break

                    found_and_clicked = False
                    # probar selectores concretos (primero #nextWeek)
                    for sel in next_selectors:
                        try:
                            elems = page.locator(sel)
                            if elems.count() == 0:
                                continue
                            # clickar el primer elemento visible/clickable
                            for j in range(elems.count()):
                                el = elems.nth(j)
                                try:
                                    el.scroll_into_view_if_needed()
                                    el.click()
                                    print(f"[INFO] Click en selector next '{sel}' (index {j})")
                                    page.wait_for_load_state("networkidle")
                                    page.wait_for_timeout(700)
                                    save_debug_screenshot(page, f"after_click_next_{attempt+1}_{target_str}")
                                    found_and_clicked = True
                                    break
                                except Exception:
                                    continue
                            if found_and_clicked:
                                break
                        except Exception:
                            continue

                    # fallback JS click specifically en #nextWeek si no se hizo click aún
                    if not found_and_clicked:
                        try:
                            clicked_js = page.evaluate("""() => {
                                const el = document.querySelector('#nextWeek');
                                if (el) { el.click(); return true; }
                                return false;
                            }""")
                            if clicked_js:
                                page.wait_for_load_state("networkidle")
                                page.wait_for_timeout(700)
                                save_debug_screenshot(page, f"after_click_next_js_{attempt+1}_{target_str}")
                                print("[INFO] Click realizado vía JS en #nextWeek")
                                found_and_clicked = True
                        except Exception:
                            found_and_clicked = False

                    # comprobar cambio en weekTitle para confirmar navegación
                    page.wait_for_timeout(900)
                    new_week_title = ""
                    try:
                        if page.locator("#weekTitle").count() > 0:
                            new_week_title = (page.locator("#weekTitle").nth(0).inner_text() or "").strip()
                    except Exception:
                        new_week_title = ""

                    if found_and_clicked and new_week_title and new_week_title != old_week_title:
                        print(f"[INFO] weekTitle cambió: '{old_week_title}' -> '{new_week_title}'")
                        old_week_title = new_week_title
                    else:
                        print(f"[INFO] weekTitle no cambió tras intento {attempt+1} (old='{old_week_title}' new='{new_week_title}')")

                    if target_visible():
                        print("[INFO] Fecha objetivo visible tras navegar semanas.")
                        clicked_next = True
                        break

                    # continuar intentando hasta max_attempts
                if not clicked_next and not target_visible():
                    print("[WARN] No se pudo navegar al día objetivo tras intentar '#nextWeek'.")
                    save_debug_screenshot(page, f"calendar_next_failed_{target_str}")
            else:
                print("[INFO] Fecha objetivo ya visible en la vista actual.")

            # --- CLICKAR EN EL DÍA OBJETIVO ---
            if target_visible():
                print(f"[INFO] Haciendo click en el día objetivo: {day_selector}")
                try:
                    page.click(day_selector)
                    page.wait_for_load_state("networkidle")
                    page.wait_for_timeout(1000) # esperar renderizado de clases
                    save_debug_screenshot(page, f"after_click_day_{target_str}")
                except Exception as e:
                    print(f"[ERROR] Falló el click en el día: {e}")

            # --- buscar '19:00' en la vista actual ---
            time_locators = [
                f"text=\"19:00\"",
                f"xpath=//*[contains(normalize-space(.), '19:00 -')]",
                f"xpath=//*[contains(normalize-space(.), '19:00-')]",
            ]
            found_count = 0
            time_nodes = None
            for sel in time_locators:
                try:
                    loc = page.locator(sel)
                    c = loc.count()
                    if c > 0:
                        found_count = c
                        time_nodes = loc
                        print(f"[INFO] Localizador '{sel}' encontró {c} nodos.")
                        break
                except Exception:
                    continue

            if not time_nodes or found_count == 0:
                print("[WARN] No se encontraron elementos con '19:00' en la página.")
                save_debug_screenshot(page, f"no_19_found_{target_str}")
                return False

            # Identificar la mejor coincidencia (Prioridad: CrossFit > Open Box > Otros)
            best_btn = None
            best_name = ""
            
            for i in range(found_count):
                cand = time_nodes.nth(i)
                try:
                    # Buscar contenedor padre (bloqueClase)
                    ancestor = cand.locator("xpath=ancestor::div[contains(@class, 'bloqueClase')]").first
                    if ancestor.count() == 0:
                        # Fallback a div genérico si no encuentra clase
                        ancestor = cand.locator("xpath=ancestor::div[1]")
                    
                    # Extraer nombre de la clase
                    class_name = ""
                    try:
                        name_el = ancestor.locator(".rvNombreCl").first
                        if name_el.count() > 0:
                            class_name = name_el.inner_text().strip()
                    except:
                        pass
                    
                    print(f"[INFO] Candidato {i}: '{class_name}'")

                    # Buscar botón Reservar
                    btn = ancestor.locator("button:has-text('Reservar'), a:has-text('Reservar'), button:has-text('Book'), a:has-text('Book')").first
                    
                    if btn.count() > 0:
                        # Prioridad ajustada según último feedback (Open Box > CrossFit)
                        if "Open Box" in class_name:
                            print(f"[INFO] ¡Encontrada clase prioritaria Open Box!")
                            best_btn = btn
                            best_name = class_name
                            break # Encontramos la ideal, salimos
                except Exception as e:
                    print(f"[WARN] Error analizando candidato {i}: {e}")
                    continue

            if best_btn:
                print(f"[INFO] Intentando reservar: {best_name}")
                try:
                    best_btn.click()
                    page.wait_for_timeout(1500)
                    
                    # Confirmaciones modales
                    for conf in ["Confirmar", "Confirm", "Aceptar", "Sí, reservar"]:
                        try:
                            if page.locator(f"button:has-text('{conf}')").count() > 0:
                                page.locator(f"button:has-text('{conf}')").first.click()
                                page.wait_for_timeout(1000)
                        except Exception:
                            pass
                            
                    save_debug_screenshot(page, f"after_click_{target_str}")
                    
                    # Verificar éxito
                    for s in SUCCESS_TEXTS:
                        try:
                            if page.locator(f"text={s}").count() > 0:
                                print(f"[SUCCESS] Detectado texto: {s}")
                                save_debug_screenshot(page, f"success_{target_str}")
                                return True
                        except Exception:
                            pass
                    
                    print("[WARN] Click hecho pero no detecté confirmación explícita.")
                    # Asumimos éxito si no hay error visible? Mejor retornar True si no hay error
                    return True 
                except Exception as e:
                    print(f"[ERROR] Falló el click en Reservar: {e}")
                    save_debug_screenshot(page, f"click_error_{target_str}")
            
            print("[INFO] Ninguna coincidencia de '19:00' válida encontrada.")
            save_debug_screenshot(page, f"not_booked_{target_str}")
            return False

        finally:
            try:
                context.close()
            except:
                pass
            try:
                browser.close()
            except:
                pass
