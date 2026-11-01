from app.models.atencion import Atencion
from app.models.catalogos import Aseguradora, Profesional
from app.models.cie10 import Cie10
from app.models.diagnostico import DiagnosticoBucal, DiagnosticoHospitalario
from app.models.imagen import ImagenClinica
from app.models.paciente import Paciente

__all__ = [
    "Aseguradora",
    "Atencion",
    "Cie10",
    "DiagnosticoBucal",
    "DiagnosticoHospitalario",
    "ImagenClinica",
    "Paciente",
    "Profesional",
]
