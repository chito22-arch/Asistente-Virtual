def preparar_ia(nombre: str) -> str:
    """Activa el agente de IA si está configurado y disponible; si no, quedan los comandos fijos.

    Devuelve un texto de estado para mostrarlo al usuario.
    """
    from ..core import activar_ia
    from .agente import Agente
    from .proveedores import crear_proveedor

    proveedor = crear_proveedor()
    if proveedor is None:
        estado = "IA: desactivada (solo comandos fijos)."
    elif not proveedor.disponible():
        estado = f"IA: {proveedor.nombre} no disponible; uso solo comandos fijos."
        if hasattr(proveedor, "modelo"):
            estado += f"\n     ¿Está Ollama instalado y el modelo descargado?  ollama pull {proveedor.modelo}"
    else:
        proveedor.precargar()
        activar_ia(Agente(proveedor, nombre))
        estado = f"IA: {proveedor.nombre} — entiendo frases libres."
    print(estado)
    return estado
