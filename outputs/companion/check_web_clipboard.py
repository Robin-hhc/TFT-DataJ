"""Embedded guide clipboard policy regression; no desktop input or clipboard writes."""
from app import QApplication, GuidePage
from PySide6.QtWebEngineCore import QWebEngineProfile,QWebEngineSettings
from PySide6.QtCore import QUrl

qt=QApplication([])
profile=QWebEngineProfile()
page=GuidePage(profile)
settings=page.settings()
assert settings.testAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard), 'Guide copy API is disabled'
assert not settings.testAttribute(QWebEngineSettings.WebAttribute.JavascriptCanPaste), 'Clipboard reading must remain disabled'
assert page.acceptNavigationRequest(QUrl('https://www.dataj.cc/comp/112'),None,True)
assert not page.acceptNavigationRequest(QUrl('https://example.com'),None,True)
page.deleteLater();qt.processEvents()
print('guide copy enabled; read/paste disabled; origin navigation restricted')
