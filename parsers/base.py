from abc import ABC, abstractmethod
import pandas as pd

class BaseParser(ABC):
    def __init__(self, pdf_path):
        self.pdf_path = pdf_path
        
    @abstractmethod
    def extract_transactions(self) -> pd.DataFrame:
        """
        Extracts transactions from the PDF and returns a standardized pandas DataFrame.
        Expected columns: Date, Description, Amount
        """
        pass
        
    @abstractmethod
    def extract_ending_balance(self) -> float:
        """
        Extracts the ending balance from the PDF.
        """
        pass
