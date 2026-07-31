import pandas as pd
from typing import List, Dict


class ExcelReader:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self._df = pd.read_excel(file_path, dtype=str)

    @property
    def headers(self) -> List[str]:
        return list(self._df.columns)

    @property
    def row_count(self) -> int:
        return len(self._df)

    def get_data(self) -> pd.DataFrame:
        return self._df.copy()

    def get_row(self, index: int) -> Dict[str, str]:
        row = self._df.iloc[index]
        return {col: str(val) if pd.notna(val) else "" for col, val in row.items()}

    def get_column(self, name: str) -> List[str]:
        return [str(v) if pd.notna(v) else "" for v in self._df[name]]
