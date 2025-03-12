from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QApplication

class FontConfig:
    """Utility class to manage fonts across the application."""
    
    _initialized = False
    _default_font = None
    _label_font = None
    
    @classmethod
    def initialize(cls):
        """Initialize fonts for the application."""
        if cls._initialized:
            return
            
        # Create default application font 
        default_font = QFont("Segoe UI")
        
        # Try each font in order until we find one that exists
        backup_fonts = [
            "Arial",
            "Helvetica",
            "MS Shell Dlg 2",
            "Liberation Sans",
            "sans-serif"
        ]
        
        # Set family using first available font
        available_families = QFontDatabase.families()
        if "Segoe UI" not in available_families:
            for font in backup_fonts:
                if font in available_families:
                    default_font.setFamily(font)
                    break
        
        # Set default font size
        default_font.setPointSize(9)
        
        # Create label font with same family but smaller size
        label_font = QFont(default_font)
        label_font.setPointSize(8)
        
        # Store fonts for reuse
        cls._default_font = default_font
        cls._label_font = label_font
        
        # Set application-wide default font
        app = QApplication.instance()
        if app:
            app.setFont(default_font)
        
        cls._initialized = True
    
    @classmethod
    def get_default_font(cls) -> QFont:
        """Get the default application font."""
        if not cls._initialized:
            cls.initialize()
        return QFont(cls._default_font)
    
    @classmethod
    def get_label_font(cls) -> QFont:
        """Get the font for labels."""
        if not cls._initialized:
            cls.initialize()
        return QFont(cls._label_font)