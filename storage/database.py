"""
Capa de Persistencia y Gestión Transaccional de Lotes (MongoDB + SQLite Offline-First).
Sistema Clasificador de Granos de Café Oro - Finca Alvizua.

Gestiona:
1. Conexión y operaciones transaccionales Offline-First (SQLite local ACID + MongoDB Atlas).
2. Sincronización asíncrona de lotes pendientes tras cortes de conectividad.
3. Purga automática de registros con retención configurable (DATA_RETENTION_DAYS).
4. Gestor de lotes con auto-cierre por inactividad (LOT_TIMEOUT_SECONDS) y cálculo de métricas derivadas (kWh, latencia).
5. Sistema de logs y alarmas de hardware (latencia de válvulas neumáticas).
"""

import os
import time
import json
import sqlite3
import logging
import threading
from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import Dict, Any, List, Optional, Tuple, Callable, Union

try:
    from pymongo import MongoClient
    from pymongo.errors import ServerSelectionTimeoutError, ConnectionFailure, PyMongoError
    import certifi
    PYMONGO_DISPONIBLE = True
except ImportError:
    MongoClient = None
    ServerSelectionTimeoutError = Exception
    ConnectionFailure = Exception
    PyMongoError = Exception
    certifi = None
    PYMONGO_DISPONIBLE = False

# =====================================================================
# 1. CONFIGURACIÓN DE LOGS Y ALARMAS DE HARDWARE
# =====================================================================

logger = logging.getLogger("MOPPI.Storage")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# Lectura de variables de entorno con valores por defecto seguros
MONGO_URI: str = os.getenv("MONGO_URI", "")
MONGO_DATABASE: str = os.getenv("MONGO_DATABASE", "moppi_clasificador")
MONGO_COLLECTION: str = os.getenv("MONGO_COLLECTION", "resumenes_lotes")
LOCAL_DB_PATH: str = os.getenv("LOCAL_DB_PATH", "storage/respaldo_local.db")
LOT_TIMEOUT_SECONDS: int = int(os.getenv("LOT_TIMEOUT_SECONDS", "60"))
DATA_RETENTION_DAYS: int = int(os.getenv("DATA_RETENTION_DAYS", "30"))
HARDWARE_POWER_KW: float = float(os.getenv("HARDWARE_POWER_KW", "0.5"))
PNEUMATIC_VALVE_LATENCY_LIMIT_MS: float = float(os.getenv("PNEUMATIC_VALVE_LATENCY_LIMIT_MS", "35.0"))
CONFIDENCE_THRESHOLD: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.35"))


def verificar_alarma_valvula(latencia_ms: float) -> bool:
    """
    Verifica si la latencia del actuador supera el límite crítico establecido.
    Emite una advertencia de alarma y retorna True si hubo transgresión.
    """
    if latencia_ms > PNEUMATIC_VALVE_LATENCY_LIMIT_MS:
        logger.warning(
            f"ALERTA HARDWARE: Latencia de válvula ({latencia_ms:.2f} ms) excede "
            f"el umbral de seguridad de {PNEUMATIC_VALVE_LATENCY_LIMIT_MS:.1f} ms."
        )
        return True
    return False


# =====================================================================
# 2. GESTOR DE PERSISTENCIA TRANSACCIONAL HÍBRIDA (DatabaseManager)
# =====================================================================

class DatabaseManager:
    """
    Gestiona la persistencia transaccional Offline-First con MongoDB Atlas y SQLite.
    Garantiza consistencia ACID local y sincronización asíncrona hacia la nube.
    """

    def __init__(
        self,
        uri_mongo: Optional[str] = None,
        nombre_db: Optional[str] = None,
        nombre_coleccion: Optional[str] = None,
        ruta_sqlite: Optional[str] = None,
        dias_retencion: Optional[int] = None,
        ruta_archivo_offline: Optional[str] = None,  # Compatibilidad con versión previa
    ) -> None:
        self.uri_mongo: str = uri_mongo if uri_mongo is not None else MONGO_URI
        self.nombre_db: str = nombre_db or MONGO_DATABASE
        self.nombre_coleccion: str = nombre_coleccion or MONGO_COLLECTION
        self.ruta_sqlite: str = ruta_sqlite or LOCAL_DB_PATH
        self.dias_retencion: int = dias_retencion if dias_retencion is not None else DATA_RETENTION_DAYS
        self.ruta_archivo_offline = ruta_archivo_offline  # Para compatibilidad con tests unitarios existentes

        self._lock = threading.RLock()
        self._cliente_mongo = None
        self._db_mongo = None
        self._coleccion_mongo = None
        self._conectado_mongo: bool = False
        self._demonio_activo: bool = False

        # 1. Asegurar directorio y crear base SQLite local
        os.makedirs(os.path.dirname(os.path.abspath(self.ruta_sqlite)), exist_ok=True)
        self._inicializar_sqlite()

        # 2. Ejecutar purga automática de datos antiguos al arranque
        try:
            self.purgar_datos_antiguos(self.dias_retencion)
        except Exception as e:
            logger.error(f"Error en purga de inicio: {e}")

        # 3. Iniciar conexión a MongoDB en segundo plano
        threading.Thread(target=self._conectar_mongo, daemon=True).start()

        # 4. Iniciar demonio de sincronización en segundo plano
        self.iniciar_demonio_sincronizacion(intervalo_segundos=20)

    @property
    def esta_conectado(self) -> bool:
        """Alias de compatibilidad para clientes existentes."""
        return self._conectado_mongo

    @property
    def esta_conectado_mongo(self) -> bool:
        """Indica si hay una conexión activa y verificada con MongoDB Atlas."""
        return self._conectado_mongo

    @contextmanager
    def _conectar_sqlite(self):
        """Crea una conexión con timeout y soporte para tipos JSON, garantizando su cierre seguro."""
        conn = sqlite3.connect(self.ruta_sqlite, timeout=10.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.row_factory = sqlite3.Row
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _inicializar_sqlite(self) -> None:
        """Crea la tabla 'lotes' e índices con garantías ACID en SQLite."""
        with self._lock:
            with self._conectar_sqlite() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS lotes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        id_lote TEXT UNIQUE NOT NULL,
                        timestamp TEXT NOT NULL,
                        fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        modelo_activo TEXT NOT NULL,
                        modo_sahi INTEGER NOT NULL DEFAULT 0,
                        duracion_segundos REAL NOT NULL,
                        duracion_formato TEXT NOT NULL,
                        consumo_kwh REAL NOT NULL,
                        potencia_nominal_kw REAL NOT NULL,
                        total_granos INTEGER NOT NULL,
                        total_sanos INTEGER NOT NULL,
                        total_defectuosos INTEGER NOT NULL,
                        porcentaje_calidad REAL NOT NULL,
                        latencia_promedio_ms REAL NOT NULL,
                        fps_promedio REAL NOT NULL,
                        conteo_crudo_json TEXT NOT NULL,
                        resumen_completo_json TEXT NOT NULL,
                        sync INTEGER NOT NULL DEFAULT 0,
                        fecha_sync TEXT
                    );
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_lotes_sync ON lotes(sync);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_lotes_fecha ON lotes(fecha_creacion);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_lotes_id ON lotes(id_lote);")
        logger.info(f"SQLite inicializado correctamente en '{self.ruta_sqlite}' (Modo WAL).")

    def _conectar_mongo(self) -> bool:
        """Establece conexión y realiza ping de salud con MongoDB Atlas con timeout de 5000 ms."""
        if not self.uri_mongo or not self.uri_mongo.startswith("mongodb"):
            logger.info("MongoDB URI no configurada. Operando exclusivamente en modo SQLite Offline.")
            self._conectado_mongo = False
            return False

        try:
            with self._lock:
                self._cliente_mongo = MongoClient(
                    self.uri_mongo,
                    serverSelectionTimeoutMS=5000,
                    connectTimeoutMS=5000,
                    socketTimeoutMS=5000,
                    tlsCAFile=certifi.where() if (certifi and hasattr(certifi, "where")) else None,
                )
                # Comando ping de validación de latencia
                self._cliente_mongo.admin.command("ping")
                self._db_mongo = self._cliente_mongo[self.nombre_db]
                self._coleccion_mongo = self._db_mongo[self.nombre_coleccion]
                self._conectado_mongo = True
                logger.info(f"Conexión exitosa a MongoDB Atlas ({self.nombre_db}.{self.nombre_coleccion}).")

            # Intentar sincronizar lotes pendientes inmediatamente
            self.sincronizar_pendientes()
            return True
        except (ServerSelectionTimeoutError, ConnectionFailure) as conn_err:
            logger.warning(
                f"Tiempo de espera agotado (5000 ms) o fallo de conexión con MongoDB Atlas: {conn_err}. "
                f"Operando en modo SQLite Offline."
            )
            self._conectado_mongo = False
            return False
        except PyMongoError as pme:
            logger.warning(f"Error de PyMongo al conectar con MongoDB Atlas: {pme}. Modo Offline activo.")
            self._conectado_mongo = False
            return False
        except Exception as e:
            logger.warning(f"No se pudo conectar a MongoDB Atlas ({e}). Modo Offline activo.")
            self._conectado_mongo = False
            return False

    def guardar_lote_transaccional(self, resumen: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Guarda el resumen del lote siguiendo la política Offline-First segura:
        1. Transacción local ACID en SQLite (sync=0).
        2. Intento de subida a MongoDB Atlas.
        3. Si la inserción en Atlas es exitosa, marca localmente sync=1.
        4. Si falla la red o timeout, se mantiene sync=0 para sincronización posterior.
        """
        id_lote = resumen.get("id_lote") or f"LOTE-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        resumen["id_lote"] = id_lote
        resumen.setdefault("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        modelo_activo = resumen.get("modelo_activo", "13_clases")
        modo_sahi = int(bool(resumen.get("modo_sahi", False)))
        duracion_seg = float(resumen.get("duracion_segundos", 0.0))
        duracion_formato = str(resumen.get("duracion_formato", "00:00:00"))
        consumo_kwh = float(resumen.get("consumo_kwh", 0.0))
        potencia_kw = float(resumen.get("potencia_nominal_kw", HARDWARE_POWER_KW))
        total_granos = int(resumen.get("total_granos", 0))
        total_sanos = int(resumen.get("total_sanos", 0))
        total_def = int(resumen.get("total_defectuosos", 0))
        calidad = float(resumen.get("porcentaje_calidad", 100.0))
        latencia_prom = float(resumen.get("latencia_promedio_ms", 0.0))
        fps_prom = float(resumen.get("fps_promedio", 0.0))

        conteo_crudo = resumen.get("conteo_crudo") or resumen.get("conteo_por_clase") or {}
        conteo_json_str = json.dumps(conteo_crudo, ensure_ascii=False)
        resumen_completo_str = json.dumps(resumen, ensure_ascii=False)

        # Paso 1: Transacción Local ACID en SQLite
        try:
            with self._lock:
                with self._conectar_sqlite() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO lotes (
                            id_lote, timestamp, modelo_activo, modo_sahi,
                            duracion_segundos, duracion_formato, consumo_kwh, potencia_nominal_kw,
                            total_granos, total_sanos, total_defectuosos, porcentaje_calidad,
                            latencia_promedio_ms, fps_promedio, conteo_crudo_json,
                            resumen_completo_json, sync, fecha_sync
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL);
                        """,
                        (
                            id_lote,
                            resumen["timestamp"],
                            modelo_activo,
                            modo_sahi,
                            duracion_seg,
                            duracion_formato,
                            consumo_kwh,
                            potencia_kw,
                            total_granos,
                            total_sanos,
                            total_def,
                            calidad,
                            latencia_prom,
                            fps_prom,
                            conteo_json_str,
                            resumen_completo_str,
                        ),
                    )
            logger.info(f"Lote {id_lote} persistido localmente en SQLite (sync=0).")
        except Exception as e:
            msg_err = f"Falla crítica en transacción SQLite para lote {id_lote}: {e}"
            logger.error(msg_err)
            if self.ruta_archivo_offline:
                self._guardar_en_archivo_offline(resumen)
            return False, msg_err

        # Si hay archivo offline en tests, respaldar también
        if self.ruta_archivo_offline:
            self._guardar_en_archivo_offline(resumen)

        # Paso 2: Intentar inserción en MongoDB Atlas
        if self._conectado_mongo and self._coleccion_mongo is not None:
            try:
                doc_mongo = dict(resumen)
                doc_mongo["_id_lote"] = id_lote
                if "_id" in doc_mongo:
                    del doc_mongo["_id"]

                res_mongo = self._coleccion_mongo.insert_one(doc_mongo)
                fecha_sinc = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # Actualizar sync=1 en SQLite
                with self._lock:
                    with self._conectar_sqlite() as conn:
                        conn.execute(
                            "UPDATE lotes SET sync=1, fecha_sync=? WHERE id_lote=?;",
                            (fecha_sinc, id_lote),
                        )

                logger.info(f"Lote {id_lote} sincronizado con MongoDB Atlas (ID: {res_mongo.inserted_id}).")
                return True, f"Guardado en MongoDB Atlas y SQLite (ID: {res_mongo.inserted_id})"
            except (ServerSelectionTimeoutError, ConnectionFailure) as conn_err:
                logger.warning(
                    f"Timeout (5000 ms) o fallo de conexión con Atlas al guardar lote {id_lote} ({conn_err}). "
                    f"Queda pendiente en SQLite (sync=0)."
                )
                self._conectado_mongo = False
            except PyMongoError as pme:
                logger.warning(
                    f"Error de PyMongo al guardar lote {id_lote} en Atlas ({pme}). Queda pendiente en SQLite."
                )
                self._conectado_mongo = False
            except Exception as e:
                logger.warning(f"Error subiendo lote {id_lote} a MongoDB Atlas ({e}). Queda pendiente en SQLite.")
                self._conectado_mongo = False

        return True, f"Guardado localmente en {self.ruta_sqlite} (Modo Offline)"

    def guardar_resumen_lote(self, resumen: Dict[str, Any]) -> Tuple[bool, str]:
        """Método de compatibilidad con código preexistente."""
        return self.guardar_lote_transaccional(resumen)

    def guardar_resumen_lote_async(
        self,
        resumen: Dict[str, Any],
        callback_resultado: Optional[Callable[[bool, str], None]] = None,
    ) -> None:
        """Guarda el lote de manera asíncrona en un hilo independiente para no congelar la UI."""
        def _tarea():
            exito, mensaje = self.guardar_lote_transaccional(resumen)
            if callback_resultado:
                callback_resultado(exito, mensaje)

        threading.Thread(target=_tarea, daemon=True).start()

    def sincronizar_pendientes(self) -> int:
        """
        Lee de la base SQLite todos los registros con sync = 0, los transforma a diccionarios
        compatibles con JSON y los sube a MongoDB Atlas utilizando insert_many().
        Transaccionalidad Estricta: Solo si MongoDB responde con éxito sin excepciones,
        ejecuta un UPDATE en SQLite cambiando el flag a sync = 1 para esos registros específicos.
        """
        # 1. Leer de SQLite todos los registros pendientes con sync = 0
        lotes_pendientes = []
        with self._lock:
            with self._conectar_sqlite() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, id_lote, resumen_completo_json FROM lotes WHERE sync = 0 ORDER BY id ASC;"
                )
                lotes_pendientes = cursor.fetchall()

        if not lotes_pendientes:
            return 0

        # 2. Transformar filas devueltas a diccionarios compatibles con JSON
        documentos_a_subir: List[Dict[str, Any]] = []
        ids_a_actualizar: List[int] = []

        for row in lotes_pendientes:
            id_registro = row["id"]
            id_lote = row["id_lote"]
            try:
                resumen_dict = json.loads(row["resumen_completo_json"])
                # Asegurar compatibilidad MongoDB eliminando cualquier _id previo
                if "_id" in resumen_dict:
                    del resumen_dict["_id"]
                resumen_dict["id_lote"] = id_lote
                documentos_a_subir.append(resumen_dict)
                ids_a_actualizar.append(id_registro)
            except Exception as e:
                logger.error(f"Error parseando JSON de lote {id_lote} para sincronización: {e}")

        if not documentos_a_subir:
            return 0

        # 3. Conexión a Atlas si no estaba activa (con timeout seguro de 5000 ms)
        if not self._conectado_mongo or self._coleccion_mongo is None:
            if not self._conectar_mongo():
                return 0

        # 4. Inserción con insert_many y Transaccionalidad Estricta
        logger.info(f"Sincronizando {len(documentos_a_subir)} lotes pendientes con MongoDB Atlas...")
        try:
            resultado = self._coleccion_mongo.insert_many(documentos_a_subir, ordered=False)

            # Transaccionalidad Estricta: Solo si MongoDB respondió con éxito
            if resultado and resultado.inserted_ids:
                fecha_sinc = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                placeholders = ",".join("?" * len(ids_a_actualizar))
                with self._lock:
                    with self._conectar_sqlite() as conn:
                        conn.execute(
                            f"UPDATE lotes SET sync = 1, fecha_sync = ? WHERE id IN ({placeholders});",
                            [fecha_sinc] + ids_a_actualizar,
                        )
                total_sincronizados = len(resultado.inserted_ids)
                logger.info(
                    f"Sincronización completada exitosamente: {total_sincronizados} lotes "
                    f"actualizados en Atlas y marcados con sync=1."
                )
                return total_sincronizados
            return 0

        except (ServerSelectionTimeoutError, ConnectionFailure) as conn_err:
            logger.warning(
                f"Fallo de conexión o timeout (5000 ms) al sincronizar con MongoDB Atlas: {conn_err}. "
                f"Sincronización en pausa; se reintentará en el próximo ciclo."
            )
            self._conectado_mongo = False
            return 0
        except PyMongoError as pme:
            logger.warning(
                f"Error de PyMongo durante sincronización de lotes: {pme}. Se reintentará en el próximo ciclo."
            )
            self._conectado_mongo = False
            return 0
        except Exception as e:
            logger.warning(
                f"Error inesperado al sincronizar lotes con MongoDB Atlas: {e}. Se reintentará en el próximo ciclo."
            )
            self._conectado_mongo = False
            return 0

    def iniciar_demonio_sincronizacion(self, intervalo_segundos: int = 20) -> None:
        """Lanza el bucle daemon para reconexión y sincronización automática en segundo plano."""
        if self._demonio_activo:
            return
        self._demonio_activo = True

        def _bucle():
            while self._demonio_activo:
                time.sleep(intervalo_segundos)
                try:
                    if not self._conectado_mongo:
                        self._conectar_mongo()
                    else:
                        self.sincronizar_pendientes()
                except (ServerSelectionTimeoutError, ConnectionFailure) as conn_err:
                    logger.warning(
                        f"Fallo de conexión en hilo de sincronización ({conn_err}). "
                        f"Reintentando en próximo ciclo."
                    )
                    self._conectado_mongo = False
                except PyMongoError as pme:
                    logger.warning(f"Error de PyMongo en hilo de sincronización: {pme}")
                    self._conectado_mongo = False
                except Exception as e:
                    logger.warning(f"Advertencia en ciclo de sincronización en segundo plano: {e}")

        threading.Thread(target=_bucle, daemon=True).start()

    def purgar_datos_antiguos(self, dias: Optional[int] = None) -> Dict[str, int]:
        """
        Elimina registros con antigüedad superior a DATA_RETENTION_DAYS (30 días)
        tanto en SQLite local como en MongoDB Atlas.
        """
        dias_limite = dias if dias is not None else self.dias_retencion
        fecha_corte = datetime.now() - timedelta(days=dias_limite)
        fecha_corte_str = fecha_corte.strftime("%Y-%m-%d %H:%M:%S")
        resultados = {"sqlite_eliminados": 0, "mongo_eliminados": 0}

        # 1. Purgar SQLite
        try:
            with self._lock:
                with self._conectar_sqlite() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "DELETE FROM lotes WHERE fecha_creacion < ? OR timestamp < ?;",
                        (fecha_corte_str, fecha_corte_str),
                    )
                    resultados["sqlite_eliminados"] = cursor.rowcount
            if resultados["sqlite_eliminados"] > 0:
                logger.info(
                    f"Purga local SQLite: {resultados['sqlite_eliminados']} registros anteriores a {dias_limite} días eliminados."
                )
        except Exception as e:
            logger.error(f"Error purgando SQLite: {e}")

        # 2. Purgar MongoDB si hay conexión
        if self._conectado_mongo and self._coleccion_mongo is not None:
            try:
                res_mongo = self._coleccion_mongo.delete_many(
                    {"timestamp": {"$lt": fecha_corte_str}}
                )
                resultados["mongo_eliminados"] = res_mongo.deleted_count
                if resultados["mongo_eliminados"] > 0:
                    logger.info(
                        f"Purga MongoDB Atlas: {resultados['mongo_eliminados']} registros anteriores a {dias_limite} días eliminados."
                    )
            except Exception as e:
                logger.warning(f"Error purgando MongoDB: {e}")

        return resultados

    def obtener_ultimos_lotes(self, limite: int = 10) -> List[Dict[str, Any]]:
        """Recupera los últimos lotes procesados desde SQLite o MongoDB."""
        # 1. Intentar desde SQLite local (inmediato, sin latencia de red)
        try:
            with self._lock:
                with self._conectar_sqlite() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT resumen_completo_json, sync FROM lotes ORDER BY id DESC LIMIT ?;",
                        (limite,),
                    )
                    filas = cursor.fetchall()
                    if filas:
                        lotes = []
                        for f in filas:
                            try:
                                d = json.loads(f["resumen_completo_json"])
                                d["_sync"] = bool(f["sync"])
                                lotes.append(d)
                            except Exception:
                                pass
                        return lotes
        except Exception as e:
            logger.debug(f"Error leyendo de SQLite ({e}), probando fallback.")

        # Fallback a MongoDB si SQLite falló
        if self._conectado_mongo and self._coleccion_mongo is not None:
            try:
                cursor_m = self._coleccion_mongo.find().sort("timestamp", -1).limit(limite)
                return list(cursor_m)
            except Exception as e:
                logger.warning(f"Error consultando lotes en MongoDB: {e}")

        # Fallback a archivo offline si existe (compatibilidad con tests)
        if self.ruta_archivo_offline and os.path.exists(self.ruta_archivo_offline):
            try:
                with open(self.ruta_archivo_offline, "r", encoding="utf-8") as f:
                    datos = json.load(f)
                    return list(reversed(datos))[:limite]
            except Exception:
                pass

        return []

    def obtener_estadisticas_acumuladas(self) -> Dict[str, Any]:
        """Calcula métricas globales históricas para las StatCards."""
        stats = {
            "total_lotes": 0,
            "total_granos": 0,
            "total_sanos": 0,
            "total_defectuosos": 0,
            "consumo_total_kwh": 0.0,
            "calidad_promedio": 100.0,
            "pendientes_sync": 0,
        }
        try:
            with self._lock:
                with self._conectar_sqlite() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        SELECT 
                            COUNT(*) as total_lotes,
                            COALESCE(SUM(total_granos), 0) as total_granos,
                            COALESCE(SUM(total_sanos), 0) as total_sanos,
                            COALESCE(SUM(total_defectuosos), 0) as total_defectuosos,
                            COALESCE(SUM(consumo_kwh), 0.0) as consumo_total_kwh,
                            COALESCE(AVG(porcentaje_calidad), 100.0) as calidad_promedio,
                            SUM(CASE WHEN sync=0 THEN 1 ELSE 0 END) as pendientes_sync
                        FROM lotes;
                        """
                    )
                    fila = cursor.fetchone()
                    if fila:
                        stats["total_lotes"] = int(fila["total_lotes"])
                        stats["total_granos"] = int(fila["total_granos"])
                        stats["total_sanos"] = int(fila["total_sanos"])
                        stats["total_defectuosos"] = int(fila["total_defectuosos"])
                        stats["consumo_total_kwh"] = round(float(fila["consumo_total_kwh"]), 4)
                        stats["calidad_promedio"] = round(float(fila["calidad_promedio"]), 2)
                        stats["pendientes_sync"] = int(fila["pendientes_sync"] or 0)
        except Exception as e:
            logger.error(f"Error calculando estadísticas globales: {e}")
        return stats

    def cerrar(self) -> None:
        """Detiene hilos de segundo plano y libera recursos."""
        self._demonio_activo = False
        if self._cliente_mongo is not None:
            try:
                self._cliente_mongo.close()
            except Exception:
                pass

    def _guardar_en_archivo_offline(self, resumen: Dict[str, Any]) -> None:
        """Guarda en archivo JSON para retrocompatibilidad con tests."""
        try:
            if not self.ruta_archivo_offline:
                return
            os.makedirs(os.path.dirname(os.path.abspath(self.ruta_archivo_offline)), exist_ok=True)
            historial = []
            if os.path.exists(self.ruta_archivo_offline):
                try:
                    with open(self.ruta_archivo_offline, "r", encoding="utf-8") as f:
                        historial = json.load(f)
                except Exception:
                    historial = []

            copia = dict(resumen)
            if "_id" in copia:
                copia["_id"] = str(copia["_id"])
            historial.append(copia)
            with open(self.ruta_archivo_offline, "w", encoding="utf-8") as f:
                json.dump(historial, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.debug(f"Error en archivo offline auxiliar: {e}")


# =====================================================================
# 3. GESTOR DE CICLO DE VIDA DE LOTES (GestorLotes)
# =====================================================================

class GestorLotes:
    """
    Controla el ciclo de vida de cada lote de clasificación:
    - Inicia y monitorea el lote activo.
    - Cierre automático si no se detectan granos por LOT_TIMEOUT_SECONDS.
    - Cierre manual mediante botón de la UI.
    - Acumula conteos según modelo activo (13 Clases vs Tri-clase).
    - Realiza cálculos derivados al cierre: kWh (potencia * tiempo), latencia media, calidad %.
    - Dispara la persistencia transaccional en DatabaseManager al cerrar el lote.
    """

    # Esquema de 13 clases del dataset
    CLASES_13: List[str] = [
        "Arabica_Agrio",
        "Arabica_Brocado",
        "Arabica_Bueno",
        "Arabica_Cereza",
        "Arabica_Concha",
        "Arabica_Inmaduro",
        "Arabica_Negro",
        "Arabica_Quebrado",
        "Robusta_Brocado",
        "Robusta_Bueno",
        "Robusta_Cereza",
        "Robusta_Negro",
        "Robusta_Quebrado",
    ]

    # Esquema de 3 clases (Modelo Campeón V10)
    CLASES_TRI: List[str] = [
        "Arabica_Bueno",
        "Robusta_Bueno",
        "Grano_Defecto",
    ]

    SANAS_GENERICAS = {"Arabica_Bueno", "Robusta_Bueno", 2, 9}

    def __init__(
        self,
        db_manager: DatabaseManager,
        timeout_inactividad_seg: Optional[int] = None,
        potencia_hardware_kw: Optional[float] = None,
        callback_lote_finalizado: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self.db_manager = db_manager
        self.timeout_inactividad_seg: int = (
            timeout_inactividad_seg if timeout_inactividad_seg is not None else LOT_TIMEOUT_SECONDS
        )
        self.potencia_hardware_kw: float = (
            potencia_hardware_kw if potencia_hardware_kw is not None else HARDWARE_POWER_KW
        )
        self.callback_lote_finalizado = callback_lote_finalizado

        self._lock = threading.RLock()
        self.modelo_13_clases: bool = False  # Tri-clase es el modelo industrial por defecto
        self.modo_sahi: bool = False

        # Estado del lote en curso
        self.lote_activo: bool = False
        self.id_lote_actual: str = ""
        self.tiempo_inicio_lote: Optional[float] = None
        self.tiempo_ultimo_grano: Optional[float] = None

        # Contadores de granos crudos y rendimiento
        self.conteo_crudo: Dict[str, int] = self._inicializar_conteo()
        self.total_granos: int = 0
        self.total_sanos: int = 0
        self.total_defectuosos: int = 0
        self.historial_latencias: List[float] = []
        self.historial_fps: List[float] = []

        # Temporizador de monitoreo de inactividad
        self._monitoreando: bool = True
        threading.Thread(target=self._bucle_monitoreo_inactividad, daemon=True).start()

    def detener(self) -> None:
        """Detiene el hilo de monitoreo de inactividad."""
        self._monitoreando = False

    def _inicializar_conteo(self) -> Dict[str, int]:
        """Crea el diccionario de conteo en cero según el modelo activo."""
        clases = self.CLASES_13 if self.modelo_13_clases else self.CLASES_TRI
        return {c: 0 for c in clases}

    def configurar_modelo(self, modelo_13_clases: bool, modo_sahi: bool) -> None:
        """Actualiza el modo de operación activo en tiempo real."""
        with self._lock:
            if self.modelo_13_clases != modelo_13_clases:
                self.modelo_13_clases = modelo_13_clases
                if not self.lote_activo:
                    self.conteo_crudo = self._inicializar_conteo()
                logger.info(
                    f"Modo de modelo actualizado: {'13 Clases' if modelo_13_clases else 'Tri-clase (Campeón V10)'}"
                )
            if self.modo_sahi != modo_sahi:
                self.modo_sahi = modo_sahi
                logger.info(f"Modo SAHI {'activado' if modo_sahi else 'desactivado'}.")

    def iniciar_nuevo_lote(self) -> str:
        """Inicia un lote de forma explícita o automática al entrar el primer grano."""
        with self._lock:
            ahora = time.time()
            self.lote_activo = True
            self.id_lote_actual = f"LOTE-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            self.tiempo_inicio_lote = ahora
            self.tiempo_ultimo_grano = ahora
            self.conteo_crudo = self._inicializar_conteo()
            self.total_granos = 0
            self.total_sanos = 0
            self.total_defectuosos = 0
            self.historial_latencias.clear()
            self.historial_fps.clear()
            logger.info(f"Lote iniciado: {self.id_lote_actual} (Modelo: {'13 Clases' if self.modelo_13_clases else 'Tri-clase'})")
            return self.id_lote_actual

    def registrar_detecciones(
        self,
        detecciones: List[Dict[str, Any]],
        fps: float,
        latencia_ms: float,
    ) -> None:
        """
        Registra el lote de detecciones del frame actual:
        - Inicia lote si no estaba activo y hay detecciones válidas.
        - Actualiza el tiempo del último grano visto para control de timeout.
        - Registra alarma si la latencia supera el límite.
        - Acumula conteos de granos.
        """
        # Validar alarma de hardware
        verificar_alarma_valvula(latencia_ms)

        if not detecciones:
            return

        with self._lock:
            ahora = time.time()
            if not self.lote_activo:
                self.iniciar_nuevo_lote()

            self.tiempo_ultimo_grano = ahora
            self.historial_fps.append(fps)
            if len(self.historial_fps) > 120:
                self.historial_fps.pop(0)

            self.historial_latencias.append(latencia_ms)
            if len(self.historial_latencias) > 120:
                self.historial_latencias.pop(0)

            for det in detecciones:
                nombre = det.get("nombre_clase", "")
                c_id = det.get("clase_id")

                self.total_granos += 1

                if self.modelo_13_clases:
                    # Enfoque 13 Clases granular
                    if nombre in self.conteo_crudo:
                        self.conteo_crudo[nombre] += 1
                    else:
                        self.conteo_crudo[nombre] = 1

                    if nombre in self.SANAS_GENERICAS or c_id in (2, 9):
                        self.total_sanos += 1
                    else:
                        self.total_defectuosos += 1
                else:
                    # Enfoque Tri-clase (Arabica_Bueno, Robusta_Bueno, Grano_Defecto)
                    if nombre in ("Arabica_Bueno", "Robusta_Bueno"):
                        self.conteo_crudo[nombre] = self.conteo_crudo.get(nombre, 0) + 1
                        self.total_sanos += 1
                    elif c_id == 2:
                        self.conteo_crudo["Arabica_Bueno"] = self.conteo_crudo.get("Arabica_Bueno", 0) + 1
                        self.total_sanos += 1
                    elif c_id == 9:
                        self.conteo_crudo["Robusta_Bueno"] = self.conteo_crudo.get("Robusta_Bueno", 0) + 1
                        self.total_sanos += 1
                    else:
                        self.conteo_crudo["Grano_Defecto"] = self.conteo_crudo.get("Grano_Defecto", 0) + 1
                        self.total_defectuosos += 1

    def _bucle_monitoreo_inactividad(self) -> None:
        """Hilo en segundo plano para verificar expiración de lote por inactividad."""
        while self._monitoreando:
            time.sleep(1.0)
            if self.lote_activo and self.tiempo_ultimo_grano is not None:
                tiempo_sin_granos = time.time() - self.tiempo_ultimo_grano
                if tiempo_sin_granos >= self.timeout_inactividad_seg:
                    logger.info(
                        f"Inactividad detectada ({tiempo_sin_granos:.1f}s >= {self.timeout_inactividad_seg}s). "
                        f"Cerrando lote {self.id_lote_actual} automáticamente."
                    )
                    self.finalizar_lote(motivo="timeout_inactividad")

    def finalizar_lote(self, motivo: str = "manual") -> Optional[Dict[str, Any]]:
        """
        Cierra el lote activo, calcula todas las métricas derivadas requeridas
        y despacha el guardado transaccional en DatabaseManager.
        """
        with self._lock:
            if not self.lote_activo or self.tiempo_inicio_lote is None:
                return None

            ahora = time.time()
            duracion_seg = max(0.1, ahora - self.tiempo_inicio_lote)
            horas_op = duracion_seg / 3600.0
            consumo_kwh = round(horas_op * self.potencia_hardware_kw, 5)

            latencia_media = (
                round(sum(self.historial_latencias) / len(self.historial_latencias), 2)
                if self.historial_latencias
                else 0.0
            )
            fps_medio = (
                round(sum(self.historial_fps) / len(self.historial_fps), 1)
                if self.historial_fps
                else 0.0
            )

            porcentaje_calidad = (
                round((self.total_sanos / self.total_granos) * 100.0, 2)
                if self.total_granos > 0
                else 100.0
            )

            segundos_int = int(duracion_seg)
            hh = segundos_int // 3600
            mm = (segundos_int % 3600) // 60
            ss = segundos_int % 60
            duracion_formato = f"{hh:02d}:{mm:02d}:{ss:02d}"

            resumen_lote = {
                "id_lote": self.id_lote_actual,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "motivo_cierre": motivo,
                "modelo_activo": "13_clases" if self.modelo_13_clases else "tri_clase",
                "modo_sahi": self.modo_sahi,
                "duracion_segundos": round(duracion_seg, 1),
                "duracion_formato": duracion_formato,
                "potencia_nominal_kw": self.potencia_hardware_kw,
                "consumo_kwh": consumo_kwh,
                "total_granos": self.total_granos,
                "total_sanos": self.total_sanos,
                "total_defectuosos": self.total_defectuosos,
                "porcentaje_calidad": porcentaje_calidad,
                "latencia_promedio_ms": latencia_media,
                "fps_promedio": fps_medio,
                "conteo_crudo": dict(self.conteo_crudo),
            }

            # Persistencia transaccional Offline-First
            self.db_manager.guardar_resumen_lote_async(resumen_lote)

            # Notificar callback de UI si fue suministrado
            if self.callback_lote_finalizado:
                try:
                    self.callback_lote_finalizado(resumen_lote)
                except Exception as e:
                    logger.error(f"Error en callback de lote finalizado: {e}")

            # Resetear estado para el siguiente lote
            self.lote_activo = False
            self.tiempo_inicio_lote = None
            self.tiempo_ultimo_grano = None
            self.conteo_crudo = self._inicializar_conteo()
            self.total_granos = 0
            self.total_sanos = 0
            self.total_defectuosos = 0

            return resumen_lote


# Alias para retrocompatibilidad con módulos existentes
MongoManager = DatabaseManager
