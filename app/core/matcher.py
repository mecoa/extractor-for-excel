import os
import glob
import pandas as pd
from string import Formatter
from typing import List, Dict, Tuple
from app.models.field import MatchRule


class FilenameMatcher:
    def __init__(self, rule: MatchRule):
        self.rule = rule

    def resolve_pattern_fields(self) -> List[str]:
        return [
            fname for _, fname, _, _ in Formatter().parse(self.rule.pattern)
            if fname is not None
        ]

    def build_filenames_from_df(self, df: pd.DataFrame) -> List[Tuple[int, str]]:
        pattern = self.rule.pattern
        match_fields = self.rule.match_fields
        results: List[Tuple[int, str]] = []

        for idx, row in df.iterrows():
            kwargs = {}
            for f in match_fields:
                val = row.get(f, "")
                kwargs[f] = str(val).strip() if pd.notna(val) else ""
            try:
                fname = pattern.format(**kwargs)
                results.append((idx, fname))
            except (KeyError, ValueError):
                results.append((idx, ""))

        return results

    def find_matching_files(self) -> Dict[str, str]:
        if not self.rule.pdf_folder or not os.path.isdir(self.rule.pdf_folder):
            return {}
        matched: Dict[str, str] = {}
        for f in os.listdir(self.rule.pdf_folder):
            matched[os.path.splitext(f)[0]] = os.path.join(self.rule.pdf_folder, f)
        return matched

    def match(self, df: pd.DataFrame) -> List[Dict]:
        pairs = self.build_filenames_from_df(df)
        available = self.find_matching_files()
        results = []
        for row_idx, gen_name in pairs:
            base = gen_name
            ext = ""
            if "." in gen_name:
                base = gen_name.rsplit(".", 1)[0]
                ext = "." + gen_name.rsplit(".", 1)[1]

            matched_path = available.get(base)
            if matched_path is None:
                for key, path in available.items():
                    if key.startswith(base) or base.startswith(key):
                        matched_path = path
                        break

            results.append({
                "row_index": row_idx,
                "generated": gen_name,
                "matched": bool(matched_path),
                "file_path": matched_path or "",
            })
        return results
