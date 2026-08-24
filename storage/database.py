"""
Capa de Persistencia (MongoDB Atlas)
Gestiona la conexión, almacenamiento de resúmenes de lote y modo offline de respaldo.
"""

import os
import json
import threading
from typing import Dict, Any, List, Optional


class MongoManager:
    """
    Gestiona la conexión y operaciones CRUD con MongoDB Atlas.
    Incluye mecanismo de tolerancia a fallos mediante guardado en búfer local si no hay conexión.
    """

    def __init__(
        self,
        uri_mongo: Optional[str] = None,
        nombre_db: str = "moppi_clasificador",
        nombre_coleccion: str = "resumenes_lotes",
        ruta_archivo_offline: str = "storage/offline_logs.json"
    ):
        """
        :param uri_mongo: Cadena de conexión mongodb+srv://... (o se lee de la variable de entorno MONGO_URI).
        :param nombre_db: Nombre de la base de datos en MongoDB Atlas.
        :param nombre_coleccion: Nombre de la colección donde se guardan los reportes de lote.
        :param ruta_archivo_offline: Ruta del archivo JSON para búfer local cuando no hay conexión.
        """
        self.uri_mongo = uri_mongo or os.getenv("MONGO_URI", "")
        self.nombre_db = nombre_db
        self.nombre_coleccion = nombre_coleccion
        self.ruta_archivo_offline = ruta_archivo_offline

        self._cliente = None
        self._db = None
        self._coleccion = None
        self._conectado = False
        self._lock = threading.RLock()

        # Intentar conexión inicial en segundo plano
        threading.Thread(target=self._conectar, daemon=True).start()

    def _conectar(self) -> bool:
        """Establece la conexión con MongoDB Atlas si la URI está presente."""
        if not self.uri_mongo or not self.uri_mongo.startswith("mongodb"):
            print("[MongoManager] URI de MongoDB no configurada. Operando en modo búfer local (offline).")
            self._conectado = False
            return False

        try:
            from pymongo import MongoClient
            import certifi
            
            with self._lock:
                self._cliente = MongoClient(
                    self.uri_mongo,
                    serverSelectionTimeoutMS=4000,
                    tlsCAFile=certifi.where() if hasattr(certifi, 'where') else None
                )
                # Probar conexión (ping)
                self._cliente.admin.command('ping')
                self._db = self._cliente[self.nombre_db]
                self._coleccion = self._db[self.nombre_coleccion]
                self._conectado = True
                print("[MongoManager] Conectado exitosamente a MongoDB Atlas.")
                
            # Si hay datos pendientes en el búfer offline, sincronizarlos
            self._sincronizar_pendientes_offline()
            return True
        except Exception as e:
            print(f"[MongoManager] Error al conectar con MongoDB Atlas ({e}). Operando en modo local.")
            self._conectado = False
            return False

    @property
    def esta_conectado(self) -> bool:
        """Indica si hay una conexión activa y verificada con MongoDB Atlas."""
        return self._conectado

    def guardar_resumen_lote_async(self, resumen: Dict[str, Any], callback_resultado = None) -> None:
        """
        Ejecuta el guardado del resumen de lote en un hilo independiente para no congelar la UI.
        """
        def _tarea():
            exito, mensaje = self.guardar_resumen_lote(resumen)
            if callback_resultado:
                callback_resultado(exito, mensaje)

        threading.Thread(target=_tarea, daemon=True).start()

    def guardar_resumen_lote(self, resumen: Dict[str, Any]) -> tuple:
        """
        Guarda el resumen en MongoDB Atlas. Si falla o no hay conexión, lo almacena en el archivo local.
        :return: (bool_exito, str_mensaje)
        """
        if self._conectado and self._coleccion is not None:
            try:
                resumen_para_db = dict(resumen)
                resultado = self._coleccion.insert_one(resumen_para_db)
                print(f"[MongoManager] Resumen insertado en Atlas con ID: {resultado.inserted_id}")
                return True, f"Guardado en MongoDB Atlas (ID: {resultado.inserted_id})"
            except Exception as e:
                print(f"[MongoManager] Falla al insertar en Atlas ({e}). Guardando en búfer local.")
                self._conectado = False
                return self._guardar_en_archivo_offline(resumen)
        else:
            return self._guardar_en_archivo_offline(resumen)

    def _guardar_en_archivo_offline(self, resumen: Dict[str, Any]) -> tuple:
        """Guarda el lote en un archivo JSON local cuando MongoDB no está disponible."""
        try:
            os.makedirs(os.path.dirname(self.ruta_archivo_offline), exist_ok=True)
            historial = []
            if os.path.exists(self.ruta_archivo_offline):
                try:
                    with open(self.ruta_archivo_offline, "r", encoding="utf-8") as f:
                        historial = json.load(f)
                except Exception:
                    historial = []

            # Asegurarse de que no haya tipos no serializables
            resumen_limpio = dict(resumen)
            if "_id" in resumen_limpio:
                resumen_limpio["_id"] = str(resumen_limpio["_id"])

            historial.append(resumen_limpio)
            with open(self.ruta_archivo_offline, "w", encoding="utf-8") as f:
                json.dump(historial, f, indent=2, ensure_ascii=False)

            return True, f"Guardado localmente en {self.ruta_archivo_offline} (Modo Offline)"
        except Exception as e:
            return False, f"Error al guardar registro local: {e}"

    def _sincronizar_pendientes_offline(self) -> None:
        """Sube a Atlas los lotes guardados localmente mientras no había conexión."""
        if not os.path.exists(self.ruta_archivo_offline) or not self._conectado:
            return

        try:
            with open(self.ruta_archivo_offline, "r", encoding="utf-8") as f:
                pendientes = json.load(f)

            if pendientes and isinstance(pendientes, list) and self._coleccion is not None:
                print(f"[MongoManager] Sincronizando {len(pendientes)} lotes pendientes con Atlas...")
                for item in pendientes:
                    if "_id" in item:
                        del item["_id"]
                    self._coleccion.insert_one(item)

                # Limpiar archivo tras sincronización exitosa
                os.remove(self.ruta_archivo_offline)
                print("[MongoManager] Sincronización offline completada.")
        except Exception as e:
            print(f"[MongoManager] Error durante la sincronización offline: {e}")

    def obtener_ultimos_lotes(self, limite: int = 5) -> List[Dict[str, Any]]:
        """Recupera los últimos lotes procesados desde Atlas o el búfer local."""
        if self._conectado and self._coleccion is not None:
            try:
                cursor = self._coleccion.find().sort("timestamp", -1).limit(limite)
                return list(cursor)
            except Exception as e:
                print(f"[MongoManager] Error recuperando lotes ({e}).")

        # Fallback a local
        if os.path.exists(self.ruta_archivo_offline):
            try:
                with open(self.ruta_archivo_offline, "r", encoding="utf-8") as f:
                    datos = json.load(f)
                    return list(reversed(datos))[:limite]
            except Exception:
                pass
        return []
