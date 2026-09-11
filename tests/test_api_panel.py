"""Qt direct-data workflow tests with synthetic clients and no network."""

from datetime import date, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLineEdit

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
    panel.cow_numbers.setText("57")
    panel._select_exact()
    selected = panel._selected_entities()
    assert [entity.number for entity in selected] == ["57"]
    panel._add_selected()
    assert panel.queue.rowCount() == 1
    assert panel.queue.item(0, 2).text() == "57"


def test_queue_keeps_individual_dates_and_same_cow_different_periods(qtbot, tmp_path):
    panel, _client, _service = connected_panel(qtbot, tmp_path)
    panel.cow_numbers.setText("57")
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
    panel._load_metrics()
    qtbot.waitUntil(lambda: panel.metrics.count() == 2)
    panel.all_metrics.setChecked(False)
    panel.metrics.item(1).setCheckState(Qt.CheckState.Unchecked)
    panel._add_selected()
    assert panel.build_request().targets[0].metrics == ("temp",)


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
