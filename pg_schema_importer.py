# -*- coding: utf-8 -*-
"""
/***************************************************************************
 PgSchemaImporter
                                 A QGIS plugin
                              -------------------
        begin                : 2026-01-28
        git sha              : $Format:%H$
        copyright            : (C) 2026 by Tobias Heini
        email                : tobias.heini@opengis.ch
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox, QProgressDialog
from qgis.core import QgsProject, QgsVectorLayer, QgsDataSourceUri, QgsProviderRegistry, QgsSettings, QgsRelationManager

# Initialize Qt resources from file resources.py
from .resources import *
# Import the code for the dialog
from .pg_schema_importer_dialog import PgSchemaImporterDialog
import os.path


class PgSchemaImporter:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'PgSchemaImporter_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&PostGISSchemaImporter')

        # Check if plugin was started the first time in current QGIS session
        # Must be set in initGui() to survive plugin reloads
        self.first_start = None

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('PgSchemaImporter', message)


    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToDatabaseMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/pg_schema_importer/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u''),
            callback=self.run,
            parent=self.iface.mainWindow())

        # will be set False in run()
        self.first_start = True


    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginDatabaseMenu(
                self.tr(u'&PostGISSchemaImporter'),
                action)
            self.iface.removeToolBarIcon(action)


    def run(self):
        """Run method that performs the main functionality of the plugin."""
        if self.first_start == True:
            self.first_start = False
            self.dlg = PgSchemaImporterDialog()
        self.dlg.show()

        # Run the dialog event loop
        result = self.dlg.exec_()

        # See if OK was pressed
        if result:
            # Get selected connection and schema
            connection_name = self.dlg.ConComboBox.currentText()
            schema_name = self.dlg.SchComboBox.currentText()
            
            if not connection_name or connection_name == "No connections found":
                QMessageBox.warning(None, "Error", "Please select a valid connection.")
                return
            
            if not schema_name:
                QMessageBox.warning(None, "Error", "Please select a schema.")
                return
            
            # Load all tables from the selected schema
            self.project = QgsProject.instance()
            self.load_schema_tables(connection_name, schema_name)

            if self.dlg.checkBox.isChecked():
                self.load_relations()
    
    def load_schema_tables(self, connection_name, schema_name):
        """Load all tables from the specified schema into QGIS."""
        try:
            # Get the postgres provider metadata
            metadata = QgsProviderRegistry.instance().providerMetadata('postgres')
            
            # Get the connection object
            conn = metadata.findConnection(connection_name)
            
            if not conn:
                QMessageBox.warning(None, "Error", f"Connection '{connection_name}' not found.")
                return
            
            # Get all tables from the schema
            tables = conn.tables(schema_name)
            
            if not tables:
                QMessageBox.information(None, "Info", f"No tables found in schema '{schema_name}'.")
                return
            
            # Counter for successfully loaded tables
            loaded_count = 0
            failed_tables = []
            
            # Create progress dialog
            progress = QProgressDialog("Loading tables...", "Cancel", 0, len(tables), None)
            progress.setWindowTitle("Importing Schema")
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumWidth(300)
            progress.show()
            
            # Load each table as a layer
            for index, table_property in enumerate(tables):
                # Check if user cancelled
                if progress.wasCanceled():
                    break
                
                table_name = table_property.tableName()
                geometry_column = table_property.geometryColumn() if table_property.geometryColumn() else None
                primary_key = table_property.primaryKeyColumns()
                
                # Update progress
                progress.setValue(index)
                progress.setLabelText(f"Loading table {index + 1} of {len(tables)}: {table_name}")
                
                # Use the connection's URI and add table/schema info
                uri = QgsDataSourceUri(conn.uri())
                
                # Set the key column if available (important for views)
                key_column = primary_key[0] if primary_key and len(primary_key) > 0 else ""
                
                # Set data source with geometry column and key
                if geometry_column:
                    uri.setDataSource(schema_name, table_name, geometry_column, "", key_column)
                else:
                    # Try without geometry column (for attribute-only tables)
                    uri.setDataSource(schema_name, table_name, None, "", key_column)
                
                # Create the vector layer
                layer = QgsVectorLayer(uri.uri(), table_name, "postgres")
                
                # If layer is not valid and we haven't specified a geometry column,
                # try to detect geometry columns automatically
                if not layer.isValid() and not geometry_column:
                    # Try common geometry column names
                    for geom_col in ['geom', 'geometry', 'the_geom', 'wkb_geometry']:
                        uri.setDataSource(schema_name, table_name, geom_col, "", key_column)
                        layer = QgsVectorLayer(uri.uri(), table_name, "postgres")
                        if layer.isValid():
                            break
                
                # Check if layer is valid
                if layer.isValid():
                    # Add layer to QGIS project
                    self.project.addMapLayer(layer)
                    loaded_count += 1
                else:
                    # Get the error message from the layer
                    error_msg = layer.error().message() if layer.error() else "Unknown error"
                    failed_tables.append(f"{table_name}: {error_msg}")
            
            # Close progress dialog
            progress.setValue(len(tables))
            progress.close()
            
            # Show summary message
            message = f"{loaded_count} tables loaded successfully."
            if failed_tables:
                message += f"\n\nFailed tables ({len(failed_tables)}): {', '.join(failed_tables)}"
            
            QMessageBox.information(None, "Import completed", message)
            
        except Exception as e:
            QMessageBox.critical(None, "Error", f"Error loading tables: {str(e)}")

    def load_relations(self):
        """Load relations from the project database and set them in the relation manager."""
        project = self.project
        relation_manager = project.relationManager()

        # 2. Get existing relations to avoid duplicates
        existing_relations = list(relation_manager.relations().values())

        # 3. List the layers you want to scan (usually all vector layers in project)
        layers = [l for l in project.mapLayers().values() if l.type() == 0] # 0 = VectorLayer

        # 4. Discover relations from the database backend
        discovered = QgsRelationManager.discoverRelations(existing_relations, layers)

        # 5. Add discovered relations to the project
        for relation in discovered:
            relation_manager.addRelation(relation)