from pydantic import BaseModel
from dataclasses import dataclass

class RegisterFunctionRequest(BaseModel):
    name: str
    image: str
    command: str

class RegisterNodeRequest(BaseModel):
    name: str
    host: str
    port: int = 22
    username: str
    password: str

@dataclass(frozen=True)
class Mode:
    value: str
    label: str

class EXECUTION_MODES:
    COLD = Mode(value="cold", label="Cold")
    PRE_WARMED = Mode(value="pre-warmed", label="Pre-warmed")
    WARMED = Mode(value="warmed", label="Warmed")

EXECUTION_MODE_MAP = {
    mode.value: mode.label
    for mode in [EXECUTION_MODES.COLD, EXECUTION_MODES.PRE_WARMED, EXECUTION_MODES.WARMED]
}