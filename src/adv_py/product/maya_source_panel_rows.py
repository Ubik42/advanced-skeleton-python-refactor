"""Keep existing native operation rows usable inside the original narrow panel."""


def fit_group_rows(group):
    from PySide2 import QtCore, QtWidgets

    class Row(QtWidgets.QLayout):
        def __init__(self):
            super().__init__()
            self.items = []
            self.setContentsMargins(0, 0, 0, 0)
            self.setSpacing(5)

        def addItem(self, item):
            self.items.append(item)

        def count(self):
            return len(self.items)

        def itemAt(self, index):
            return self.items[index] if 0 <= index < len(self.items) else None

        def takeAt(self, index):
            return self.items.pop(index) if 0 <= index < len(self.items) else None

        def expandingDirections(self):
            return QtCore.Qt.Horizontal

        def hasHeightForWidth(self):
            return True

        def heightForWidth(self, width):
            return self.arrange(QtCore.QRect(0, 0, width, 0), apply=False)

        def sizeHint(self):
            return self.minimumSize()

        def minimumSize(self):
            size = QtCore.QSize()
            for item in self.items:
                size = size.expandedTo(item.minimumSize())
            return size

        def setGeometry(self, rect):
            super().setGeometry(rect)
            self.arrange(rect, apply=True)

        def arrange(self, rect, *, apply):
            x, y, height = rect.x(), rect.y(), 0
            for item in self.items:
                size = item.sizeHint().expandedTo(item.minimumSize())
                if x != rect.x() and x + size.width() > rect.right() + 1:
                    x, y, height = rect.x(), y + height + self.spacing(), 0
                if apply:
                    item.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), size))
                x += size.width() + self.spacing()
                height = max(height, size.height())
            return y + height - rect.y()

    for combo in group.findChildren(QtWidgets.QComboBox):
        combo.setMinimumContentsLength(12)
        combo.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
    for check in group.findChildren(QtWidgets.QCheckBox):
        text = check.text()
        if check.fontMetrics().horizontalAdvance(text) <= 250:
            continue
        lines, current = [], ''
        for char in text:
            if current and check.fontMetrics().horizontalAdvance(current + char) > 250:
                lines.append(current)
                current = ''
            current += char
        check.setText('\n'.join((*lines, current)))
        check.setAccessibleName(text)
        check.setToolTip(text)

    def visit(layout):
        # QFormLayout appends a replacement item to its internal item list;
        # visit backwards so removal cannot skip the next original row.
        for index in range(layout.count() - 1, -1, -1):
            item = layout.itemAt(index)
            child = item.layout()
            if child is None:
                continue
            visit(child)
            if not isinstance(child, QtWidgets.QHBoxLayout):
                continue
            row = Row()
            while child.count():
                row.addItem(child.takeAt(0))
            if isinstance(layout, QtWidgets.QFormLayout):
                position, role = layout.getItemPosition(index)
                layout.takeAt(index)
                layout.setLayout(position, role, row)
            else:
                layout.takeAt(index)
                layout.insertLayout(index, row)
            child.deleteLater()
    # Some original rows are wrapped in QWidget holders (file fields and
    # native button rows). Reflow those holders, not Qt's internal controls.
    for widget in group.findChildren(QtWidgets.QWidget):
        if (type(widget) is QtWidgets.QWidget and widget.layout() is not None
                and not widget.objectName().startswith('qt_')):
            child = widget.layout()
            visit(child)
            if isinstance(child, QtWidgets.QHBoxLayout):
                discard = QtWidgets.QWidget()
                discard.setLayout(child)
                row = Row()
                while child.count():
                    row.addItem(child.takeAt(0))
                widget.setLayout(row)
                discard.deleteLater()
    visit(group.layout())
