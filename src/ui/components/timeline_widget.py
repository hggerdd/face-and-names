from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor
from PyQt6.QtCore import Qt, QPoint
from datetime import datetime
import logging

class TimelineWidget(QWidget):
    """Widget that displays a timeline of face occurrences."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(100)
        self.setMaximumHeight(100)
        self.timeline_data = []  # List of (date, count) tuples
        self.min_date = None
        self.max_date = None
        self.max_count = 0
        
    def update_data(self, image_dates):
        """Update timeline with new image dates."""
        if not image_dates:
            self.timeline_data = []
            self.update()
            return
            
        # Group dates by month and count occurrences
        date_counts = {}
        for date_str in image_dates:
            try:
                # Handle common EXIF date formats
                formats = [
                    "%Y:%m:%d %H:%M:%S",  # Standard EXIF format
                    "%Y-%m-%d %H:%M:%S",  # Alternative format
                ]
                
                date = None
                for fmt in formats:
                    try:
                        date = datetime.strptime(date_str, fmt)
                        break
                    except ValueError:
                        continue
                
                if date is None:
                    logging.warning(f"Could not parse date: {date_str}")
                    continue
                    
                month_key = date.replace(day=1, hour=0, minute=0, second=0)
                date_counts[month_key] = date_counts.get(month_key, 0) + 1
            except Exception as e:
                logging.warning(f"Invalid date format: {date_str} - {e}")
                continue
        
        if not date_counts:
            return
            
        # Sort by date
        self.timeline_data = sorted(date_counts.items())
        self.min_date = min(date_counts.keys())
        self.max_date = max(date_counts.keys())
        self.max_count = max(date_counts.values())
        self.update()
    
    def paintEvent(self, event):
        if not self.timeline_data:
            return
            
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Calculate dimensions
        padding = 30  # Increased padding for better text visibility
        width = self.width() - 2 * padding
        height = self.height() - 2 * padding
        
        # Draw timeline base
        painter.setPen(QPen(Qt.GlobalColor.gray, 2))
        painter.drawLine(padding, self.height() - padding, 
                        self.width() - padding, self.height() - padding)
        
        # Draw year markers if timeline spans multiple years
        years_span = self.max_date.year - self.min_date.year
        if years_span > 0:
            painter.setPen(QPen(Qt.GlobalColor.gray))
            for year in range(self.min_date.year, self.max_date.year + 1):
                date = datetime(year, 1, 1)
                if date >= self.min_date and date <= self.max_date:
                    x_pos = self._get_x_position(date, width, padding)
                    painter.drawLine(int(x_pos), self.height() - padding,
                                   int(x_pos), self.height() - padding + 5)
                    painter.drawText(int(x_pos - 20), self.height() - 5, str(year))
        
        # Draw circles for each month with data
        for date, count in self.timeline_data:
            x_pos = self._get_x_position(date, width, padding)
            
            # Calculate circle size based on count
            max_radius = min(25, height // 2)  # Slightly smaller maximum radius
            radius = max(4, int(max_radius * (count / self.max_count)))
            
            # Draw circle
            y_pos = self.height() - padding - radius
            painter.setBrush(QBrush(QColor(70, 130, 180, 200)))  # Steel blue, semi-transparent
            painter.setPen(QPen(Qt.GlobalColor.darkBlue))
            painter.drawEllipse(QPoint(int(x_pos), int(y_pos)), radius, radius)
            
            # Draw count if circle is large enough
            if radius > 10:
                painter.setPen(QPen(Qt.GlobalColor.white))
                painter.drawText(QPoint(int(x_pos - 4), int(y_pos + 4)), str(count))
        
        # Draw start and end dates
        painter.setPen(QPen(Qt.GlobalColor.black))
        painter.drawText(padding, self.height() - padding - height - 5, 
                        self.min_date.strftime("%Y-%m"))
        right_text = self.max_date.strftime("%Y-%m")
        right_width = painter.fontMetrics().horizontalAdvance(right_text)
        painter.drawText(self.width() - padding - right_width, 
                        self.height() - padding - height - 5,
                        right_text)
    
    def _get_x_position(self, date, width, padding):
        """Calculate x position for a given date."""
        date_range = (self.max_date - self.min_date).total_seconds()
        if date_range == 0:
            return padding + width // 2
        else:
            return padding + width * (date - self.min_date).total_seconds() / date_range