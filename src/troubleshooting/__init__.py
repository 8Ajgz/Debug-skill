"""Troubleshooting skill - 5-phase universal methodology"""
from .phases_5 import Troubleshooter, DiagnosisResult
from .diagnostics import (
    UniversalTroubleshooter,
    ToolDiagnostician,
    HealthChecker,
    DiagnosisReport,
    diagnose_problem,
    check_tool_health,
)

__version__ = "1.0.0"
__all__ = [
    'Troubleshooter', 'DiagnosisResult',
    'UniversalTroubleshooter', 'ToolDiagnostician', 'HealthChecker', 'DiagnosisReport',
    'diagnose_problem', 'check_tool_health',
]
