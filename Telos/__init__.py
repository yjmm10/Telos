
__version__ = "0.1.0"
__project__ = "Telos"

from Telos.data import IMG_FORMATS,MetaFile
# from Telos.utils import check_source
from Telos.core import CVModel,YOLOv8,LatexOCR,DBNet,CRNN,ReadingOrder
from Telos.config import *
from Telos.modules import Layout,DetFormula,OCR

__all__ = (
    "__version__",
    "__project__",
    "IMG_FORMATS",
    "MetaFile",
    "CVModel",
    "YOLOv8",
    "Layout",
    "DetFormula",
    "LatexOCR",
    "DBNet",
    "CRNN",
    "OCR",
    "ReadingOrder",
)