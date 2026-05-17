"""
RF2 - Gestion de Ingresos y Egresos
Autor: Rodri Petez

Modulo de logica de negocio puro (sin UI).
Provee funciones para que RF3, RF4 y RF5 puedan consumir los datos.
"""

import uuid
import json
import os
from datetime import datetime, date
from typing import Optional

# ── RUTA DEL ARCHIVO JSON ────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DATA_DIR    = os.path.join(BASE_DIR, "data")
DATA_FILE   = os.path.join(DATA_DIR, "movimientos.json")

# ── LISTENERS (para notificar cambios a RF3 y RF4) ────────────────
_listeners: list = []

def registrar_listener(callback) -> None:
    """
    RF3 y RF4 llaman a esta funcion para suscribirse a cambios.
    Cada vez que se crea, modifica o elimina un movimiento,
    se llama automaticamente a todos los callbacks registrados.

    Uso desde RF3:
        from movimientos import registrar_listener
        registrar_listener(panel_general.actualizar)
    """
    if callback not in _listeners:
        _listeners.append(callback)

def _notificar() -> None:
    """Uso interno: avisa a todos los listeners que los datos cambiaron."""
    for cb in _listeners:
        try:
            cb()
        except Exception:
            pass


# ════════════════════════════════════════════════════════════════════
# PERSISTENCIA JSON
# ════════════════════════════════════════════════════════════════════

def _cargar() -> list[dict]:
    """Lee el archivo JSON y devuelve la lista de movimientos."""
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        datos = json.load(f)
    return datos.get("movimientos", [])


def _guardar(movimientos: list[dict]) -> None:
    """Persiste la lista completa en el archivo JSON."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump({"movimientos": movimientos}, f, ensure_ascii=False, indent=2)


# ════════════════════════════════════════════════════════════════════
# RF2.1 / RF2.2 — REGISTRO DE INGRESO Y EGRESO
# ════════════════════════════════════════════════════════════════════

def registrar_movimiento(
    tipo: str,
    monto: float,
    categoria_id: str,
    categoria_nombre: str,
    fecha_movimiento: str,
    descripcion: str = ""
) -> dict:
    """
    RF2.1 — Registra un ingreso.
    RF2.2 — Registra un egreso.

    Parametros:
        tipo              : "ingreso" o "egreso"
        monto             : valor numerico positivo (RF2.3)
        categoria_id      : ID de la categoria (viene de RF1)
        categoria_nombre  : nombre legible de la categoria (viene de RF1)
        fecha_movimiento  : fecha en que ocurrio el movimiento "YYYY-MM-DD"
        descripcion       : texto libre opcional (RF2.3)

    Retorna el movimiento creado como dict.
    Lanza ValueError si los datos son invalidos.
    """
    _validar_tipo(tipo)
    _validar_monto(monto)
    _validar_fecha(fecha_movimiento)

    movimiento = {
        "id":               str(uuid.uuid4()),          # RF2.3 — ID unico, invisible para el usuario
        "tipo":             tipo,
        "monto":            round(float(monto), 2),
        "descripcion":      descripcion.strip(),
        "fecha_movimiento": fecha_movimiento,           # RF2.3 — fecha del movimiento
        "fecha_creacion":   _timestamp_ahora(),         # RF2.3 — timestamp automatico, no editable
        "categoria_id":     categoria_id,
        "categoria_nombre": categoria_nombre,
    }

    todos = _cargar()
    todos.append(movimiento)
    _guardar(todos)
    _notificar()
    return movimiento


# ════════════════════════════════════════════════════════════════════
# RF2.4 — CALCULADORA DE COMPOSICION DE MONTO
# ════════════════════════════════════════════════════════════════════

def calcular_monto_compuesto(items: list[dict]) -> float:
    """
    RF2.4 — Suma varios montos parciales y devuelve el total.

    Parametros:
        items: lista de dicts con la forma:
               [{"descripcion": "Supermercado", "monto": 3500},
                {"descripcion": "Verduleria",   "monto": 800}, ...]

    Retorna el total redondeado a 2 decimales.
    Lanza ValueError si algun item tiene monto invalido o la lista esta vacia.

    Uso tipico: llamar antes de registrar_movimiento() para obtener el monto final.
    """
    if not items:
        raise ValueError("Debe haber al menos un item para calcular el monto.")

    total = 0.0
    for i, item in enumerate(items):
        monto = item.get("monto")
        if monto is None:
            raise ValueError(f"El item {i+1} no tiene monto.")
        if not isinstance(monto, (int, float)) or monto <= 0:
            raise ValueError(f"El monto del item {i+1} debe ser un numero positivo.")
        total += float(monto)

    return round(total, 2)


# ════════════════════════════════════════════════════════════════════
# RF2.5 — MODIFICACION DE INGRESO/EGRESO
# ════════════════════════════════════════════════════════════════════

def modificar_movimiento(
    id_movimiento: str,
    nuevo_monto: Optional[float]  = None,
    nueva_fecha: Optional[str]    = None,
    nueva_descripcion: Optional[str] = None
) -> dict:
    """
    RF2.5 — Modifica monto, fecha y/o descripcion de un movimiento existente.
    No se puede cambiar: tipo, categoria, fecha_creacion ni id.

    Parametros:
        id_movimiento    : ID del registro a modificar
        nuevo_monto      : nuevo valor (opcional)
        nueva_fecha      : nueva fecha "YYYY-MM-DD" (opcional)
        nueva_descripcion: nuevo texto (opcional)

    Retorna el movimiento actualizado.
    Lanza ValueError si el ID no existe o los datos son invalidos.
    """
    todos = _cargar()
    idx   = _buscar_indice(todos, id_movimiento)

    if nuevo_monto is not None:
        _validar_monto(nuevo_monto)
        todos[idx]["monto"] = round(float(nuevo_monto), 2)

    if nueva_fecha is not None:
        _validar_fecha(nueva_fecha)
        todos[idx]["fecha_movimiento"] = nueva_fecha

    if nueva_descripcion is not None:
        todos[idx]["descripcion"] = nueva_descripcion.strip()

    _guardar(todos)
    _notificar()
    return todos[idx]


# ════════════════════════════════════════════════════════════════════
# RF2.6 — BAJA DE INGRESO/EGRESO
# ════════════════════════════════════════════════════════════════════

def eliminar_movimiento(id_movimiento: str) -> None:
    """
    RF2.6 — Elimina un movimiento por su ID.
    Lanza ValueError si el ID no existe.
    """
    todos = _cargar()
    _buscar_indice(todos, id_movimiento)   # valida que exista
    todos = [m for m in todos if m["id"] != id_movimiento]
    _guardar(todos)
    _notificar()


def eliminar_movimientos(ids: list[str]) -> int:
    """
    RF2.6 — Elimina varios movimientos en lote.
    Retorna la cantidad efectivamente eliminada.
    """
    todos    = _cargar()
    ids_set  = set(ids)
    restantes = [m for m in todos if m["id"] not in ids_set]
    eliminados = len(todos) - len(restantes)
    _guardar(restantes)
    if eliminados > 0:
        _notificar()
    return eliminados


# ════════════════════════════════════════════════════════════════════
# RF2.7 — PROGRAMACION DE REGISTROS
# ════════════════════════════════════════════════════════════════════

def programar_movimiento(
    tipo: str,
    monto: float,
    categoria_id: str,
    categoria_nombre: str,
    fecha_movimiento: str,
    descripcion: str = "",
    frecuencia: str  = "unica"
) -> dict:
    """
    RF2.7 — Programa un movimiento para una fecha futura o pasada.
    Si la fecha ya paso o es hoy, el movimiento se registra directamente.
    Si es futura, queda guardado con fecha_movimiento en el futuro
    y sera procesado al abrir la app (ver procesar_programados()).

    Parametros:
        frecuencia: "unica" o "mensual"
    """
    _validar_tipo(tipo)
    _validar_monto(monto)
    _validar_fecha(fecha_movimiento)
    if frecuencia not in ("unica", "mensual"):
        raise ValueError("frecuencia debe ser 'unica' o 'mensual'.")

    hoy = date.today().isoformat()

    # si la fecha es presente o pasada, se registra como ejecutado normal
    if fecha_movimiento <= hoy:
        return registrar_movimiento(
            tipo, monto, categoria_id, categoria_nombre,
            fecha_movimiento, descripcion
        )

    # si es futura, se guarda con campo extra "programado"
    movimiento = {
        "id":               str(uuid.uuid4()),
        "tipo":             tipo,
        "monto":            round(float(monto), 2),
        "descripcion":      descripcion.strip(),
        "fecha_movimiento": fecha_movimiento,
        "fecha_creacion":   _timestamp_ahora(),
        "categoria_id":     categoria_id,
        "categoria_nombre": categoria_nombre,
        "programado":       True,
        "frecuencia":       frecuencia,
    }

    todos = _cargar()
    todos.append(movimiento)
    _guardar(todos)
    return movimiento


def procesar_programados() -> list[dict]:
    """
    RF2.7 — Ejecuta todos los movimientos programados cuya fecha ya vencio.
    Llamar al iniciar la aplicacion.
    Retorna la lista de movimientos que fueron procesados.
    """
    todos    = _cargar()
    hoy      = date.today().isoformat()
    nuevos   = []
    procesados = []

    for m in todos:
        if not m.get("programado"):
            nuevos.append(m)
            continue

        if m["fecha_movimiento"] <= hoy:
            # ejecutar: sacar flag programado
            m_ejecutado = {k: v for k, v in m.items()
                           if k not in ("programado", "frecuencia")}
            nuevos.append(m_ejecutado)
            procesados.append(m_ejecutado)

            # si es mensual, generar el proximo
            if m.get("frecuencia") == "mensual":
                prox = _siguiente_mes(m["fecha_movimiento"])
                nuevo_prog = {**m, "id": str(uuid.uuid4()),
                              "fecha_movimiento": prox,
                              "fecha_creacion": _timestamp_ahora()}
                nuevos.append(nuevo_prog)
        else:
            nuevos.append(m)

    if procesados:
        _guardar(nuevos)
        _notificar()

    return procesados


def cancelar_programado(id_movimiento: str) -> None:
    """RF2.7 — Cancela un movimiento programado antes de que se ejecute."""
    todos = _cargar()
    idx   = _buscar_indice(todos, id_movimiento)
    if not todos[idx].get("programado"):
        raise ValueError("El movimiento no esta programado.")
    todos.pop(idx)
    _guardar(todos)


# ════════════════════════════════════════════════════════════════════
# FUNCIONES PUBLICAS PARA RF3, RF4 y RF5
# ════════════════════════════════════════════════════════════════════

def get_todos() -> list[dict]:
    """Retorna todos los movimientos ejecutados (excluye programados futuros)."""
    return [m for m in _cargar() if not m.get("programado")]


def get_movimientos_por_mes(mes: int, anio: int) -> list[dict]:
    """
    Para RF3 — Panel General.
    Retorna todos los movimientos ejecutados del mes y anio indicados,
    ordenados por fecha_movimiento descendente.
    """
    prefijo = f"{anio}-{str(mes).zfill(2)}"
    resultado = [
        m for m in get_todos()
        if m["fecha_movimiento"].startswith(prefijo)
    ]
    return sorted(resultado, key=lambda m: m["fecha_movimiento"], reverse=True)


def get_ingresos_del_mes(mes: int, anio: int) -> list[dict]:
    """Para RF5 — PDF. Retorna solo los ingresos del mes."""
    return [m for m in get_movimientos_por_mes(mes, anio) if m["tipo"] == "ingreso"]


def get_egresos_del_mes(mes: int, anio: int) -> list[dict]:
    """Para RF5 — PDF. Retorna solo los egresos del mes."""
    return [m for m in get_movimientos_por_mes(mes, anio) if m["tipo"] == "egreso"]


def get_total_ingresos(mes: int, anio: int) -> float:
    """Para RF3 — Panel General. Suma de todos los ingresos del mes."""
    return round(sum(m["monto"] for m in get_ingresos_del_mes(mes, anio)), 2)


def get_total_egresos(mes: int, anio: int) -> float:
    """Para RF3 — Panel General. Suma de todos los egresos del mes."""
    return round(sum(m["monto"] for m in get_egresos_del_mes(mes, anio)), 2)


def get_balance(mes: int, anio: int) -> float:
    """Para RF3 — Panel General. Balance = ingresos - egresos del mes."""
    return round(get_total_ingresos(mes, anio) - get_total_egresos(mes, anio), 2)


def get_movimientos_agrupados_por_categoria(tipo: str, mes: int, anio: int) -> dict:
    """
    Para RF4 — Grafico de torta.
    Retorna un dict {nombre_categoria: monto_total} del tipo y mes indicados.

    Ejemplo de retorno:
        {"Alimentacion": 4500.0, "Transporte": 1200.0, "Salud": 800.0}
    """
    movs    = get_movimientos_por_mes(mes, anio)
    filtros = [m for m in movs if m["tipo"] == tipo]
    agrupado: dict[str, float] = {}
    for m in filtros:
        cat = m["categoria_nombre"]
        agrupado[cat] = round(agrupado.get(cat, 0.0) + m["monto"], 2)
    return agrupado


def get_movimientos_agrupados_por_mes(anio: int) -> dict:
    """
    Para RF4 — Grafico de barras.
    Retorna un dict con totales de ingresos y egresos por mes del anio.

    Ejemplo de retorno:
        {
          "2025-01": {"ingresos": 50000.0, "egresos": 32000.0},
          "2025-02": {"ingresos": 48000.0, "egresos": 29500.0},
          ...
        }
    """
    prefijo = str(anio)
    movs    = [m for m in get_todos() if m["fecha_movimiento"].startswith(prefijo)]
    agrupado: dict[str, dict] = {}

    for m in movs:
        clave = m["fecha_movimiento"][:7]   # "YYYY-MM"
        if clave not in agrupado:
            agrupado[clave] = {"ingresos": 0.0, "egresos": 0.0}
        agrupado[clave][m["tipo"] + "s"] = round(
            agrupado[clave][m["tipo"] + "s"] + m["monto"], 2
        )

    return dict(sorted(agrupado.items()))


def get_programados() -> list[dict]:
    """Retorna todos los movimientos que aun estan pendientes de ejecutarse."""
    return [m for m in _cargar() if m.get("programado")]


# ════════════════════════════════════════════════════════════════════
# VALIDACIONES INTERNAS
# ════════════════════════════════════════════════════════════════════

def _validar_tipo(tipo: str) -> None:
    if tipo not in ("ingreso", "egreso"):
        raise ValueError(f"tipo debe ser 'ingreso' o 'egreso'. Se recibio: '{tipo}'")

def _validar_monto(monto) -> None:
    if not isinstance(monto, (int, float)) or monto <= 0:
        raise ValueError("El monto debe ser un numero positivo mayor a cero.")

def _validar_fecha(fecha: str) -> None:
    try:
        datetime.strptime(fecha, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Formato de fecha invalido: '{fecha}'. Use YYYY-MM-DD.")

def _buscar_indice(lista: list[dict], id_movimiento: str) -> int:
    for i, m in enumerate(lista):
        if m["id"] == id_movimiento:
            return i
    raise ValueError(f"No se encontro ningun movimiento con id: '{id_movimiento}'")

def _timestamp_ahora() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

def _siguiente_mes(fecha_str: str) -> str:
    """Dado 'YYYY-MM-DD', retorna la misma fecha del mes siguiente."""
    dt = datetime.strptime(fecha_str, "%Y-%m-%d")
    mes = dt.month + 1
    anio = dt.year + (1 if mes > 12 else 0)
    mes  = 1 if mes > 12 else mes
    # ajustar dia si el mes siguiente tiene menos dias
    import calendar
    ultimo_dia = calendar.monthrange(anio, mes)[1]
    dia = min(dt.day, ultimo_dia)
    return f"{anio}-{str(mes).zfill(2)}-{str(dia).zfill(2)}"