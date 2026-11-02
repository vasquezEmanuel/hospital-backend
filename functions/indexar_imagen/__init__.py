"""Función de indexación de imágenes (Fase 4 del documento técnico). Carpeta: functions/indexar_imagen/.

nucleo.py   -> lógica independiente del proveedor de nube (decide a qué paciente pertenece cada archivo).
handler.py  -> adaptador para eventos de almacenamiento compatibles con S3 (AWS S3, Cloudflare R2, MinIO...).
reindexar.py -> la misma lógica para una lista de claves, para indexar archivos que ya estaban en el almacenamiento.
"""
