"""Generated module 1 for a large-PR smoke test. Do not merge."""

from dataclasses import dataclass

@dataclass
class Record1_0:
    name: str
    value: int

    def doubled(self) -> int:
        return self.value * 2

    def label(self) -> str:
        return f"{self.name}={self.value}"

@dataclass
class Record1_1:
    name: str
    value: int

    def doubled(self) -> int:
        return self.value * 2

    def label(self) -> str:
        return f"{self.name}={self.value}"

@dataclass
class Record1_2:
    name: str
    value: int

    def doubled(self) -> int:
        return self.value * 2

    def label(self) -> str:
        return f"{self.name}={self.value}"

@dataclass
class Record1_3:
    name: str
    value: int

    def doubled(self) -> int:
        return self.value * 2

    def label(self) -> str:
        return f"{self.name}={self.value}"

@dataclass
class Record1_4:
    name: str
    value: int

    def doubled(self) -> int:
        return self.value * 2

    def label(self) -> str:
        return f"{self.name}={self.value}"

@dataclass
class Record1_5:
    name: str
    value: int

    def doubled(self) -> int:
        return self.value * 2

    def label(self) -> str:
        return f"{self.name}={self.value}"

@dataclass
class Record1_6:
    name: str
    value: int

    def doubled(self) -> int:
        return self.value * 2

    def label(self) -> str:
        return f"{self.name}={self.value}"

@dataclass
class Record1_7:
    name: str
    value: int

    def doubled(self) -> int:
        return self.value * 2

    def label(self) -> str:
        return f"{self.name}={self.value}"

@dataclass
class Record1_8:
    name: str
    value: int

    def doubled(self) -> int:
        return self.value * 2

    def label(self) -> str:
        return f"{self.name}={self.value}"

@dataclass
class Record1_9:
    name: str
    value: int

    def doubled(self) -> int:
        return self.value * 2

    def label(self) -> str:
        return f"{self.name}={self.value}"

@dataclass
class Record1_10:
    name: str
    value: int

    def doubled(self) -> int:
        return self.value * 2

    def label(self) -> str:
        return f"{self.name}={self.value}"

@dataclass
class Record1_11:
    name: str
    value: int

    def doubled(self) -> int:
        return self.value * 2

    def label(self) -> str:
        return f"{self.name}={self.value}"

@dataclass
class Record1_12:
    name: str
    value: int

    def doubled(self) -> int:
        return self.value * 2

    def label(self) -> str:
        return f"{self.name}={self.value}"

@dataclass
class Record1_13:
    name: str
    value: int

    def doubled(self) -> int:
        return self.value * 2

    def label(self) -> str:
        return f"{self.name}={self.value}"

@dataclass
class Record1_14:
    name: str
    value: int

    def doubled(self) -> int:
        return self.value * 2

    def label(self) -> str:
        return f"{self.name}={self.value}"

@dataclass
class Record1_15:
    name: str
    value: int

    def doubled(self) -> int:
        return self.value * 2

    def label(self) -> str:
        return f"{self.name}={self.value}"

@dataclass
class Record1_16:
    name: str
    value: int

    def doubled(self) -> int:
        return self.value * 2

    def label(self) -> str:
        return f"{self.name}={self.value}"

@dataclass
class Record1_17:
    name: str
    value: int

    def doubled(self) -> int:
        return self.value * 2

    def label(self) -> str:
        return f"{self.name}={self.value}"


import pickle


def load_session(blob: bytes):
    # deserializing untrusted input executes arbitrary code
    return pickle.loads(blob)
