"""Qt direct-data workflow tests with synthetic clients and no network."""

from datetime import date, timedelta

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import QAbstractItemView, QLineEdit

from smaxtec.application.api_data import (
    ApiCatalog,
    ApiDownloadResult,
    ApiEntity,
    ApiFarm,
    ApiMetric,
)
from smaxtec.ui.api_panel import ApiPanel


class Client:
    def __init__(self):
        self.farm = ApiFarm("farm-synthetic-001", "Synthetic Farm", "Europe/London")
        self.entities = (
            ApiEntity("animal-synthetic-057", "animals", self.farm, "57", "57"),
            ApiEntity("animal-synthetic-657", "animals", self.farm, "657", "New girl"),
        )
        self.disconnected = False

    def connect(self, credentials, stop):
        assert credentials.username == "analyst@example.test"
        assert credentials.password == "synthetic-password"
        return (self.farm,)

    def catalog(self, farm, archived, stop):
        return ApiCatalog(farm, self.entities, (), ())

    def metrics(self, entity, stop):
        if entity.number == "657":
            return (ApiMetric("temp", ("celsius",)), ApiMetric("rumination", ("minutes",)))
        return (ApiMetric("temp", ("celsius",)), ApiMetric("act", ("index",)))

    def disconnect(self):
        self.disconnected = True


class Service:
    def __init__(self, folder):
        self.folder = folder
        self.requests = []

    def download(self, request, stop, progress):
        self.requests.append(request)
        return ApiDownloadResult(self.folder, (), 0)


def connected_panel(qtbot, tmp_path):
    client = Client()
    service = Service(tmp_path)
    panel = ApiPanel(client=client, service=service)
    qtbot.addWidget(panel)
    panel.username.setText("analyst@example.test")
    panel.password.setText("synthetic-password")
    panel._connect()
    qtbot.waitUntil(lambda: panel._connected)
    panel.farm.setCurrentIndex(1)
    qtbot.waitUntil(lambda: panel._catalog is not None)
    panel.destination.setText(str(tmp_path))
    return panel, client, service


def test_password_is_masked_cleared_and_exact_cow_selection_never_matches_657(qtbot, tmp_path):
    panel, _client, _service = connected_panel(qtbot, tmp_path)
    assert panel.password.echoMode() == QLineEdit.EchoMode.Password
    assert panel.password.text() == ""
    panel.cow_numbers.setPlainText("57")
    panel._select_exact()
    selected = panel._selected_entities()
    assert [entity.number for entity in selected] == ["57"]
    panel._add_selected()
    assert panel.queue.rowCount() == 1
    assert panel.queue.item(0, 2).text() == "57"


def test_queue_keeps_individual_dates_and_same_cow_different_periods(qtbot, tmp_path):
    panel, _client, _service = connected_panel(qtbot, tmp_path)
    panel.cow_numbers.setPlainText("57")
    panel._select_exact()
    panel.shared_from.setText("01/09/2026")
    panel.shared_to.setText("02/09/2026")
    panel._add_selected()
    panel.shared_from.setText("05/09/2026")
    panel.shared_to.setText("07/09/2026")
    panel._add_selected()
    request = panel.build_request()
    assert [(item.start_date, item.end_date) for item in request.targets] == [
        (date(2026, 9, 1), date(2026, 9, 2)),
        (date(2026, 9, 5), date(2026, 9, 7)),
    ]
    assert [item.entity.number for item in request.targets] == ["57", "57"]


def test_discovered_measurements_can_be_frozen_into_queue(qtbot, tmp_path):
    panel, _client, _service = connected_panel(qtbot, tmp_path)
    panel.inventory.selectRow(0)
    panel._add_selected()
    panel.queue.selectRow(0)
    panel._load_metrics()
    qtbot.waitUntil(lambda: panel.metrics.count() == 2)
    assert not panel.all_metrics.isChecked()
    panel.metrics.item(1).setCheckState(Qt.CheckState.Unchecked)
    panel._apply_metrics()
    assert panel.build_request().targets[0].metrics == ("temp",)


def test_queue_discovers_common_metrics_and_applies_only_to_selected_rows(qtbot, tmp_path):
    panel, _client, _service = connected_panel(qtbot, tmp_path)
    panel.inventory.selectAll()
    panel._add_selected()
    assert panel.queue.rowCount() == 2

    panel.queue.selectAll()
    panel._load_metrics()
    qtbot.waitUntil(lambda: not panel.is_busy)
    assert panel.metrics.count() == 1
    assert panel.metrics.item(0).data(Qt.ItemDataRole.UserRole) == "temp"
    assert "every one of the 2 selected targets" in panel.metric_note.text()
    panel._apply_metrics()
    assert [target.metrics for target in panel.build_request().targets] == [("temp",), ("temp",)]

    panel.queue.clearSelection()
    panel.queue.selectRow(0)
    panel.all_metrics.setChecked(True)
    panel._apply_metrics()
    assert [target.metrics for target in panel.build_request().targets] == [(), ("temp",)]


def test_inventory_and_queue_use_ordinary_click_multi_selection(qtbot, tmp_path):
    panel, _client, _service = connected_panel(qtbot, tmp_path)
    assert panel.inventory.selectionMode() == QAbstractItemView.SelectionMode.MultiSelection
    assert panel.queue.selectionMode() == QAbstractItemView.SelectionMode.MultiSelection
    assert panel.inventory.minimumHeight() == 340
    assert panel.account_fields.isHidden()
    assert not panel.disconnect_button.isHidden()


def test_bulk_cow_paste_and_filtered_selection_are_exact_alternatives(qtbot, tmp_path):
    panel, _client, _service = connected_panel(qtbot, tmp_path)
    panel.cow_numbers.setPlainText("57\n657, 57")
    panel._select_exact()
    assert [entity.number for entity in panel._selected_entities()] == ["57", "657"]

    panel.search.setText("65")
    panel._select_shown()
    assert [entity.number for entity in panel._selected_entities()] == ["657"]


def test_queue_viewport_expands_for_large_batches(qtbot, tmp_path):
    panel, _client, _service = connected_panel(qtbot, tmp_path)
    panel.inventory.selectAll()
    panel._add_selected()
    assert panel.queue.minimumHeight() == 220
    for _ in range(4):
        panel._add_selected()
    assert panel.queue.rowCount() == 10
    assert panel.queue.minimumHeight() == 380


def test_panel_disconnect_releases_client_and_queue(qtbot, tmp_path):
    panel, client, _service = connected_panel(qtbot, tmp_path)
    panel.inventory.selectRow(0)
    panel._add_selected()
    panel.disconnect()
    qtbot.waitUntil(lambda: not panel.is_busy)
    assert client.disconnected
    assert panel.queue.rowCount() == 0
    assert not panel._connected


def test_reviewed_queue_runs_download_off_ui_thread(qtbot, tmp_path, monkeypatch):
    panel, _client, service = connected_panel(qtbot, tmp_path)
    panel.inventory.selectRow(0)
    panel._add_selected()
    monkeypatch.setattr(
        "smaxtec.ui.api_panel.ApiReviewDialog.exec",
        lambda _dialog: _dialog.DialogCode.Accepted,
    )
    panel._review_download()
    qtbot.waitUntil(lambda: len(service.requests) == 1)
    qtbot.waitUntil(lambda: not panel.is_busy)
    assert service.requests[0].targets[0].entity.number == "57"
    assert panel.result_summary.text().startswith("Collection finished")
    assert panel._last_folder == tmp_path


def test_future_date_in_farm_timezone_is_rejected(qtbot, tmp_path):
    panel, _client, _service = connected_panel(qtbot, tmp_path)
    panel.inventory.selectRow(0)
    future = date.today() + timedelta(days=1)
    panel.shared_from.setText(future.strftime("%d/%m/%Y"))
    panel.shared_to.setText(future.strftime("%d/%m/%Y"))
    panel._add_selected()
    assert panel.queue.rowCount() == 0
    assert "future" in panel.status.text()


def test_short_window_scrolls_workflow_pages_without_compressing_or_overlapping(qtbot, tmp_path):
    panel, _client, _service = connected_panel(qtbot, tmp_path)
    panel.resize(760, 560)
    panel.show()
    qtbot.waitUntil(lambda: panel.browse_scroll.verticalScrollBar().maximum() > 0)

    def rectangle(widget, page):
        return QRect(widget.mapTo(page, QPoint(0, 0)), widget.size())

    def assert_below(upper, lower, page):
        assert rectangle(upper, page).bottom() < rectangle(lower, page).top()

    assert_below(panel.search, panel.inventory, panel.browse_page)
    assert_below(panel.inventory, panel.select_shown_button, panel.browse_page)
    assert_below(panel.select_shown_button, panel.cow_numbers, panel.browse_page)
    assert_below(panel.cow_numbers, panel.shared_from, panel.browse_page)
    for control in (
        panel.farm,
        panel.search,
        panel.shared_from,
        panel.add_button,
    ):
        assert control.height() >= control.sizeHint().height()
    assert panel.cow_numbers.height() >= panel.cow_numbers.minimumHeight()

    panel.steps.setCurrentIndex(1)
    qtbot.waitUntil(lambda: panel.queue_scroll.verticalScrollBar().maximum() > 0)
    assert_below(panel.queue, panel.remove_button, panel.queue_page)
    assert_below(panel.remove_button, panel.metrics, panel.queue_page)
    assert_below(panel.metrics, panel.destination, panel.queue_page)
    assert_below(panel.destination, panel.collection_name, panel.queue_page)
    for control in (
        panel.queue,
        panel.remove_button,
        panel.metrics,
        panel.destination,
        panel.collection_name,
        panel.download_button,
    ):
        assert control.height() >= control.minimumSizeHint().height()
