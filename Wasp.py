# title           :wasp.py
#description     :3D Slicer plugin to perform watershed and annotation
#author          :Thomas lawson (MRC)
#date            :2014-08-07
#version         :0.1
#usage           :To be run IN 3D slicer. Cannot be run outside of 3D Slicer
#formatting      :As many of the functions and classes used are from C++, the C++ naming convention has been used
#python_version  :2.7
#=============================================================================

from __main__ import vtk, qt, ctk, slicer
import re
import sys
import SimpleITK as sitk
import sitkUtils
import numpy as np
import threading
import os
import unittest
import Queue
from time import sleep


class Wasp:
    def __init__(self, parent):
        parent.title = "(WASP) Watershed Annotation and Segmentation Plugin"
        parent.categories = ["SIG"]
        parent.dependencies = []
        parent.contributors = ["Tom Lawson (MRC)"]
        parent.helpText = """
        A module to perform a series of ITK watershed segmentation and then filter and select segmented volumes which are of interest

        todo:
        * Add user error checks, e.g incorrect file, incorrect parameters
        * More unit-testing
        """
        parent.acknowledgementText = """
        MRC Harwell, UK
        Systems Imaging Group
        Supervisor: Henrik Westerberg

        Additional thanks
        Nicole Aucoin <nicole@bwh.harvard.edu> kindly answered some questions in the dev mailing list
        """
        self.parent = parent

        # Add this test to the SelfTest module's list for discovery when the module
        # is created.  Since this module may be discovered before SelfTests itself,
        # create the list if it doesn't already exist.
        try:
            slicer.selfTests
        except AttributeError:
            slicer.selfTests = {}
            slicer.selfTests['Wasp'] = self.runTest

        def runTest(self):
            tester = testTest()
            tester.runTest()


class WaspWidget:
    def __init__(self, parent=None):
        if not parent:
            self.parent = slicer.qMRMLWidget()
            self.parent.setLayout(qt.QVBoxLayout())
            self.parent.setMRMLScene(slicer.mrmlScene)
        else:
            self.parent = parent
            self.layout = self.parent.layout()
        if not parent:
            self.setup()
            self.parent.show()

    def updateStatusLabel(self, msg):
        """
        Updates a label at the bottom of the plugin
        :param str msg: Containing message to be printed
        """
        self.currentStatusLabel.setText(msg)

    def progressBarUpdate(self, msg):
        """
        Updates a progress bar at the bottom of the plugin. Set up to use progress monitoring from SimpleITK
        :param int msg: The value for the progress bar
        """
        try:
            int(msg)
            self.progress.setValue(msg)
        except ValueError:
            print "progress callback not an int"

    def progressShow(self):
        """ Displays the progress bar at the bottom of the plugin """
        self.progress.show()

    def progressHide(self):
        """ Hides the progress bar at the bottom of the plugin, also resets to zero"""
        self.progress.setValue(0)
        self.progress.hide()

    def test(self):
        print "it works "

    def setup(self):
        """
        Setup of the plugin, Uses ctk, qt and slicer objects. Consists of three sections
            1. Reload and testing: Only used for testing and can be removed
            2. Watershed: Performs the gradient magnitude filter and watershed filter on the original data
            3. Annotation: Allows a user to select out components by using fiducials
        """
        ##################################################
        # Reload and testing (only used for development)
        ##################################################
        self.reloadCollapsibleButton = ctk.ctkCollapsibleButton()
        self.reloadCollapsibleButton.text = "Reload && Test"
        self.layout.addWidget(self.reloadCollapsibleButton)
        self.reloadFormLayout = qt.QFormLayout(self.reloadCollapsibleButton)

        # reload button
        # (use this during development, but remove it when delivering
        #  your module to users)
        self.reloadButton = qt.QPushButton("Reload")
        self.reloadButton.toolTip = "Reload this module."
        self.reloadButton.name = "test Reload"
        self.reloadFormLayout.addWidget(self.reloadButton)
        self.reloadButton.connect('clicked()', self.onReload)

        # reload and test button
        # (use this during development, but remove it when delivering
        #  your module to users)
        self.reloadAndTestButton = qt.QPushButton("Reload and Test")
        self.reloadAndTestButton.toolTip = "Reload this module and then run the self tests."
        self.reloadFormLayout.addWidget(self.reloadAndTestButton)
        self.reloadAndTestButton.connect('clicked()', self.onReloadAndTest)
        #self.layout.addStretch(1)


        ##################################################
        # Watershed
        ##################################################
        # Collapsible button
        self.wsCollapsibleButton = ctk.ctkCollapsibleButton()
        self.wsCollapsibleButton.text = "Perform watershed"
        self.layout.addWidget(self.wsCollapsibleButton)

        # Layout within the collapsible button
        self.wsFormLayout = qt.QFormLayout(self.wsCollapsibleButton)

        # Volume setup
        # make a frame enclosed by a collapsible button
        self.frame = qt.QFrame(self.wsCollapsibleButton)
        # Set ANOTHER layout in the frame
        self.frame.setLayout(qt.QHBoxLayout())
        self.wsFormLayout.addRow(self.frame)
        self.inputSelector = qt.QLabel("Input Volume: ", self.frame)
        self.frame.layout().addWidget(self.inputSelector)
        self.inputSelector = slicer.qMRMLNodeComboBox(self.frame)
        self.inputSelector.nodeTypes = ( ("vtkMRMLScalarVolumeNode"), "" )
        self.inputSelector.addEnabled = False
        self.inputSelector.removeEnabled = False
        self.inputSelector.setMRMLScene(slicer.mrmlScene)
        self.frame.layout().addWidget(self.inputSelector)

        # Gradient magnitude level
        self.gradLabel = qt.QLabel("Gradient sigma:")
        self.wsFormLayout.addWidget(self.gradLabel)
        self.gradSig = qt.QDoubleSpinBox()
        self.gradSig.minimum = 0.01
        self.gradSig.value = 1.20
        self.gradSig.setSingleStep(0.01)
        self.wsFormLayout.addWidget(self.gradSig)

        # watershed iteration
        self.wsIterationLabel = qt.QLabel("Watershed iteration steps:")
        self.wsFormLayout.addRow(self.wsIterationLabel)
        self.wsIteration = qt.QDoubleSpinBox()
        self.wsIteration.minimum = 0.1
        self.wsIteration.value = 0.1
        self.wsIteration.setSingleStep(0.1)
        self.wsFormLayout.addWidget(self.wsIteration)

        # filter the output
        self.filterLabel = qt.QLabel("Filter out segmentations where the total pixel count is less than:")
        self.wsFormLayout.addRow(self.filterLabel)
        self.filterBy = qt.QLineEdit("10")
        self.filterBy = qt.QSpinBox()
        self.filterBy.minimum = 0
        self.filterBy.maximum = 1000000
        self.filterBy.value = 10
        self.filterBy.setSingleStep(1)
        self.wsFormLayout.addWidget(self.filterBy)

        # ws level
        self.wsLevelLabel = qt.QLabel("Watershed level:")
        self.wsLevelLabel.setToolTip("Set the range for the watershed level")
        self.wsFormLayout.addRow(self.wsLevelLabel)
        self.wsLevel = ctk.ctkRangeWidget()
        self.wsLevel.spinBoxAlignment = 0xff  # put enties on top
        self.wsLevel.singleStep = 0.1
        self.wsLevel.maximum = 10
        self.wsLevel.maximumValue = 4
        self.wsLevel.minimumValue = 0.2
        self.wsFormLayout.addRow(self.wsLevel)

        # Apply button
        goButton = qt.QPushButton("Go")
        goButton.toolTip = "Run the ws Operator."
        self.wsFormLayout.addRow(goButton)
        goButton.connect('clicked(bool)', self.onApplyWS)

        # Cancel button
        self.cancelButtonWS = qt.QPushButton("Cancel")
        self.cancelButtonWS.toolTip = "Stop Everything!"
        self.wsFormLayout.addRow(self.cancelButtonWS)
        self.cancelButtonWS.connect('clicked(bool)', self.onCancelButton)

        ##################################################
        # Annotation
        ##################################################
        # Collapsible button
        self.annotationCollapsibleButton = ctk.ctkCollapsibleButton()
        self.annotationCollapsibleButton.text = "Annotation"
        self.layout.addWidget(self.annotationCollapsibleButton)

        # Layout within the collapsible button
        self.annotationFormLayout = qt.QFormLayout(self.annotationCollapsibleButton)

        # Fiducial input
        # make a frame enclosed by a collapsible button
        self.frame2 = qt.QFrame(self.annotationCollapsibleButton)
        # Set ANOTHER layout in the frame
        self.frame2.setLayout(qt.QHBoxLayout())
        self.annotationFormLayout.addRow(self.frame2)
        self.inputFiducialsNodeSelector = qt.QLabel("Input Fiducials: ", self.frame2)
        self.frame2.layout().addWidget(self.inputFiducialsNodeSelector)
        self.inputFiducialsNodeSelector = slicer.qMRMLNodeComboBox(self.frame2)
        self.inputFiducialsNodeSelector.nodeTypes = ['vtkMRMLMarkupsFiducialNode', 'vtkMRMLAnnotationHierarchyNode',
                                                     'vtkMRMLFiducialListNode']
        self.inputFiducialsNodeSelector.addEnabled = False
        self.inputFiducialsNodeSelector.removeEnabled = False
        self.inputFiducialsNodeSelector.setMRMLScene(slicer.mrmlScene)
        self.frame2.layout().addWidget(self.inputFiducialsNodeSelector)

        # Output for filtered label map
        self.outputFrame = qt.QFrame(self.annotationCollapsibleButton)
        self.outputFrame.setLayout(qt.QHBoxLayout())
        self.annotationFormLayout.addWidget(self.outputFrame)
        self.outputSelector = qt.QLabel("Output Annotated label map: ", self.outputFrame)
        self.outputFrame.layout().addWidget(self.outputSelector)
        self.outputSelector = slicer.qMRMLNodeComboBox(self.outputFrame)
        self.outputSelector.nodeTypes = ["vtkMRMLScalarVolumeNode"]
        self.outputSelector.addEnabled = True
        self.outputSelector.removeEnabled = True
        self.outputSelector.renameEnabled = True
        self.outputSelector.setMRMLScene(slicer.mrmlScene)
        self.outputFrame.layout().addWidget(self.outputSelector)

        # reference labels input
        self.refFrame = qt.QFrame(self.annotationCollapsibleButton)
        self.refFrame.setLayout(qt.QHBoxLayout())
        self.annotationFormLayout.addRow(self.refFrame)
        self.refLabel = qt.QLabel("Reference label map order [Optional]: ", self.refFrame)
        self.refFrame.layout().addWidget(self.refLabel)
        self.refSelector = slicer.qMRMLNodeComboBox(self.refFrame)
        self.refSelector.nodeTypes = ['vtkMRMLColorNode']  # Dont know a node type for just .txt
        self.refSelector.addEnabled = False
        self.refSelector.noneEnabled = True
        self.refSelector.removeEnabled = False
        self.refSelector.setMRMLScene(slicer.mrmlScene)
        self.refSelector.toolTip = "OPTIONAL:" \
                                   "Can reorder the naming of the labels. " \
                                   "Requires at a text file where the first column is a number and the second column " \
                                   "is the label used for the fiducial e.g. 1 liver" \
                                   "                                        2 lung"
        self.refFrame.layout().addWidget(self.refSelector)

        # Apply button
        goButtonAnn = qt.QPushButton("Go")
        goButtonAnn.toolTip = "Run the Annotation."
        self.annotationFormLayout.addRow(goButtonAnn)
        goButtonAnn.connect('clicked(bool)', self.onApplyAnnotation)

        # Cancel button
        cancelButtonAnn = qt.QPushButton("Cancel")
        cancelButtonAnn.toolTip = "Stop Everything!"
        self.annotationFormLayout.addRow(cancelButtonAnn)
        cancelButtonAnn.connect('clicked(bool)', self.onCancelButton)

        ##################################################
        # Status and Progress
        ##################################################
        # Label
        statusLabel = qt.QLabel("Status: ")
        self.currentStatusLabel = qt.QLabel("Idle")
        hlayout = qt.QHBoxLayout()
        hlayout.addStretch(1)
        hlayout.addWidget(statusLabel)
        hlayout.addWidget(self.currentStatusLabel)
        self.layout.addLayout(hlayout)

        # Progress bar
        self.progress = qt.QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.layout.addWidget(self.progress)
        self.progress.hide()

    def onApplyWS(self):
        """
        When the Go button is pressed in the "perform watershed" section an instance of a WaspLogic class is created and
        the runWS method is run.
        """
        volumeNode = self.inputSelector.currentNode()

        # the WaspLogic should be able to be run from the slicer python command line
        self.logic = WaspLogic()

        # perform the watershed
        self.logic.runWS(volumeNode,
                         float(self.gradSig.text),
                         float(self.wsIteration.text),
                         self.wsLevel.minimumValue,
                         self.wsLevel.maximumValue,
                         int(self.filterBy.text))

    def onApplyAnnotation(self):
        """
        When the Go button is pressed in the annotation section an instance of the WaspLogic class is created and the
        runAnn method is run
        """
        # get fiducial, output and ref nodes
        fiducialNode = self.inputFiducialsNodeSelector.currentNode()
        outputVolumeNode = self.outputSelector.currentNode()
        refNode = self.refSelector.currentNode()

        # Run the annotation stuff
        self.logic = WaspLogic()
        self.logic.runAnn(fiducialNode, outputVolumeNode, refNode)


    def onCancelButton(self):
        """
        Method called when the Cancel button is pressed in either the annotation or watershed section. Cancels
        all processes. Doesn't currently stop model making.
        """
        self.currentStatusLabel.setText("Aborted")
        self.progress.hide()
        if self.logic:
            self.logic.abort = True

    def onLogicEventAbort(self):
        """
        Call from logic. Just sets the status level to aborted.
        """
        self.currentStatusLabel.setText("Aborted")

    def onLogicEventProgress(self, progress, name):
        """
        Called from logic. Displays the simpleITK progress
        :param float progress: simpleitk progress
        :param str name: what simpleitk process is occuring
        """
        self.currentStatusLabel.setText("Running " + name + " ({0:6.5f})".format(progress))
        self.progress.setValue(progress * 100)

    def onLogicEventStart(self):
        """ Called from logic. Displayed when simpleitk process started """
        self.currentStatusLabel.text = "Running"
        self.progress.setValue(0)
        self.progress.show()

    def onLogicEventEnd(self):
        """ Called from logic. Displayed when simpleitk process ended"""
        self.currentStatusLabel.text = "Completed"
        self.progress.setValue(100)

    def delayDisplay(self, message, msec=1000):
        """ Widgit function to update display. Same function used in the WaspLogic section. Most probably deprecated
        here

        :param str message: Message to show user
        :param int msec: How long message is displayed for
        """
        print(message)
        self.info = qt.QDialog()
        self.infoLayout = qt.QVBoxLayout()
        self.info.setLayout(self.infoLayout)
        self.label = qt.QLabel(message, self.info)
        self.infoLayout.addWidget(self.label)
        qt.QTimer.singleShot(msec, self.info.close)
        self.info.exec_()

    def onReload(self, moduleName="Wasp"):
        """Generic reload method for any scripted module.
        ModuleWizard will subsitute correct default moduleName.
        """
        globals()[moduleName] = slicer.util.reloadScriptedModule(moduleName)

    def onReloadAndTest(self, moduleName="Wasp"):
        try:
            self.onReload()
            evalString = 'globals()["%s"].%sTest()' % (moduleName, moduleName)
            tester = eval(evalString)
            tester.runTest()
        except Exception, e:
            import traceback

            traceback.print_exc()
            qt.QMessageBox.warning(slicer.util.mainWindow(),
                                   "Reload and Test",
                                   'Exception!\n\n' + str(e) + "\n\nSee Python Console for Stack Trace")

class WaspLogic:
    """ Implements the computation done by your module.

    Main functionality as follows:

    * Performs a series of watershed segmentations based on the parameters given from the GUI
    * Makes a combined label map from a set of fiducials

    Can be imported by other python code and function without an instance of the widget
    """

    def __init__(self):
        """ Initialises queues and abort switch """
        self.main_queue = Queue.Queue()
        self.main_queue_running = False
        self.thread = threading.Thread()
        self.abort = False

    def __del__(self):
        """ Stops anything running in the thread queue """
        if self.main_queue_running:
            self.main_queue_stop
        if self.thread.is_alive():
            self.thread.join()

    def hasImageData(self, volumeNode):
        """This is a dummy logic method that
        returns true if the passed in volume
        node has valid image data
        """
        if not volumeNode:
            print('no volume node')
            return False
        if volumeNode.GetImageData() == None:
            print('no image data')
            return False

        return True

    def delayDisplay(self, message, msec=1000):
        """ Logic version to update display. Same function used in the WaspLogic section. Most probably deprecated
        here

        :param str message: Message to show user
        :param int msec: How long message is displayed for
        """
        print(message)
        self.info = qt.QDialog()
        self.infoLayout = qt.QVBoxLayout()
        self.info.setLayout(self.infoLayout)
        self.label = qt.QLabel(message, self.info)
        self.infoLayout.addWidget(self.label)
        qt.QTimer.singleShot(msec, self.info.close)
        self.info.exec_()

    def runWS(self, volumeNode, gradSig, iteration, minValue, maxValue, filterBy):
        """ Run the watershed section

        :param obj volumeNode: 3D slicer volume object
        :param float gradSig: sigma value used for gradient filter
        :param float iteration: Value of steps used in between the selected range
        :param float minValue: Min value used for the watershed level
        :param float maxValue: Max value used for the watershed level
        :param int filterBy: Mininum number of pixels required for each segmentation
        """
        self.delayDisplay('Running watershed program')

        # Get parameters and save them as instance variables
        self.imgNodeName = volumeNode.GetName()
        self.gradSig = gradSig
        self.iteration = iteration
        self.minValue = minValue
        self.maxValue = maxValue
        self.filterBy = filterBy

        # Start the thread (so can run in the background)
        self.thread = threading.Thread(target=lambda: self.threadWS())
        self.main_queue_start()
        self.thread.start()

        return True


    def threadWS(self):
        """ Performs all of the analysis required for the watershed stage.

        Uses SimpleITK for the processing.
        """
        nIter = 0
        #####################################
        # Reading in image
        #####################################
        slicer.modules.WaspWidget.updateStatusLabel("Reading image in")
        sitkReader = sitk.ImageFileReader()
        sitkReader = self.sitkProgress(sitkReader, "reading")
        sitkReader.SetFileName(sitkUtils.GetSlicerITKReadWriteAddress(self.imgNodeName))
        img = sitkReader.Execute()

        #####################################
        # Get the gradient magnitude image
        #####################################
        print "doing gradient"
        feature_img = self.gradientFilter(img)
        self.makeSlicerObject(feature_img, ("gradient_mag"), label=False)

        #####################################
        # Performing watershed loop
        #####################################
        #numpy array of ws levels
        ws_list = np.arange(self.minValue, (self.maxValue + float(self.iteration)), float(self.iteration))
        print "ws levels:", ws_list

        # Loop through the range of watershed values choosen
        for y in ws_list:

            if self.abort:
                return

            sitk_ws = self.wsFilter(feature_img, y)

            # relabel
            sitk_relabel = self.relabelFilter(sitk_ws)

            # sitk to slicer conversion
            self.makeSlicerObject(sitk_relabel, ("ws_level" + str(y)), label=True)

        slicer.modules.WaspWidget.progressHide()
        slicer.modules.WaspWidget.updateStatusLabel("Idle")

        # this filter is persistent, remove commands
        print "done"
        self.main_queue.put(self.main_queue_stop)

    def runAnn(self, fiducialNode, outputVolumeNode, refNode):
        """ Run the annotation section.

        From a list of fiducials identifies which label map the fiducial is reference from. Then gets the label map
        value for the region.

        Does this for all of the fiducials and creates a new label map based on all of the selected segmentation.

        Then creates a 3D model of this label map.

        :param obj fiducialNode: The fiducials used to identify the components
        :param obj outputVolumeNode: The output label map
        :param obj refNode:
            Defaulted to a none Slicer object. A user can choose the order the labels and fiducials are named
        """
        self.delayDisplay('Running program')

        # The mainAnn performs the main processing to create a new label map
        # I could have saved the parameters as instance attrubtes like in runWS but have sent them as parameters into
        # mainAnn here.
        self.mainAnn(fiducialNode, outputVolumeNode, refNode)

        # Now can make a model of the annotation.
        self.makeModel(outputVolumeNode.GetName(), outputVolumeNode)

        return True

    def mainAnn(self, fiducialNode, outputVolumeNode, refNode):
        """ Run the actuall processing for the annotation section.

        :param obj fiducialNode: The fiducials used to identify the components
        :param obj outputVolumeNode: The output label map
        :param obj refNode:
            Defaulted to a none Slicer object. A user can choose the order the labels and fiducials are named
        """
        # Need the widget for some messages
        widget = slicer.modules.WaspWidget

        # The simpleitk process are all run on seperate threads. I use the queue module to keep track of them
        self.main_queue_start()

        # Check if there is actually fiducials
        try:
            num_fid = fiducialNode.GetNumberOfFiducials()
            new_label_map = None
        except AttributeError as e:
            print e
            self.main_queue.put(lambda: widget.delayDisplay("No fiducial selected"))
            self.yieldPythonGIL()
            return

        # if no fiducials stop and tell user
        if num_fid == 0:
            self.main_queue.put(lambda: widget.delayDisplay("No fiducials within fiducial set"))
            self.yieldPythonGIL()
            return

        # fiducials dict
        f_dict = {}

        # component list
        comp_list = []

        # Loop through the fiducials
        for i in xrange(num_fid):

            # Print the current fiducial
            print i

            # Get the volume associated with this fiducial
            volumeID = fiducialNode.GetNthFiducialAssociatedNodeID(i)
            lab = fiducialNode.GetNthFiducialLabel(i)
            print lab
            volumeNode = slicer.util.getNode(volumeID)
            print volumeNode.GetName()

            # Set up coordinates
            coordsRAS = [0, 0, 0, 0]
            coordsXYZ = [0, 0, 0]

            # Get RAS coordinates (saved in list coordsRAS)
            fiducialNode.GetNthFiducialWorldCoordinates(i, coordsRAS)

            # Don't need the last data point for our purposes
            del coordsRAS[-1]

            # This bit here is taken and modified from the dataprobe.py slicer module.
            sliceNode = slicer.mrmlScene.GetNthNodeByClass(0, 'vtkMRMLSliceNode')
            appLogic = slicer.app.applicationLogic()
            sliceLogic = appLogic.GetSliceLogic(sliceNode)
            layerLogic = sliceLogic.GetForegroundLayer()

            # Get the xyz coordinates
            slicer.vtkMRMLAbstractSliceViewDisplayableManager.ConvertRASToXYZ(sliceNode, coordsRAS, coordsXYZ)

            # Get the IJK coordinates
            xyToIJK = layerLogic.GetXYToIJKTransform()
            coordsIJK = xyToIJK.TransformDoublePoint(coordsXYZ)

            # Make into int
            coordsIJK = map(int, coordsIJK)

            print coordsRAS
            print coordsXYZ
            print coordsIJK

            # Add to fiducial dictionary
            f_dict[lab] = (coordsIJK)

            # Read in as a simpleitk object
            sitkReader = sitk.ImageFileReader()
            sitkReader.SetNumberOfThreads(8)
            sitkReader = self.sitkProgress(sitkReader, "reading")
            sitkReader.SetFileName(sitkUtils.GetSlicerITKReadWriteAddress(volumeNode.GetName()))
            img = sitkReader.Execute()

            # Get the pixel value for the fiducial coordinates. The pixel value is equivalent to the label or
            # can be called component
            component_num = img.GetPixel(*coordsIJK)
            print "component num", component_num

            comp_list.append(int(component_num))

            # Check if the fiducials is on a watershed line or background
            # background is 1 typically 1 from the watershed result. But if an external non-watershed label map is
            # to be used this check would be annoying. Therefore I do a regex check to see if it is a ws_level
            # result from WASP.
            if (int(component_num) == 1 and re.search("ws_level", lab)) or int(component_num) == 0:
                print "###incorrect value selected for fiducials###"
                err = ('Incorrect value used for one of the fiducials.'+os.linesep+
                        'Cannot have a label that is background (pixel value 1) '
                        'or watershed line (pixel value 0).'+os.linesep+os.linesep+
                        'Please check:'+os.linesep+
                        'Fiducial: '+str(lab)+os.linesep+
                        'Label map: '+str(volumeNode.GetName())+os.linesep)

                self.main_queue.put(lambda: widget.delayDisplay(err, msec=100000))
                self.yieldPythonGIL()
                self.main_queue.put(self.main_queue_stop)
                slicer.modules.WaspWidget.progressHide()
                return
            else:
                # Get simpleitk object of the watershed
                new_component = (img == component_num)

                # This adds all the components selected together
                if not new_label_map:
                    print "make the label map"
                    # should only occur once
                    new_label_map = new_component
                else:
                    print "add to label map"
                    new_label_map = (new_label_map + new_component)

            print " "

        # separate into components again
        print "connected component"
        sitkConnected = sitk.ConnectedComponentImageFilter()
        sitkConnected = self.sitkProgress(sitkConnected, "Connecting_components")
        connected = sitkConnected.Execute(new_label_map)

        # Order the new label map nicely
        print "reorder"
        sitkRelabel = sitk.RelabelComponentImageFilter()
        sitkRelabel = self.sitkProgress(sitkRelabel, "Relabel")
        relabelled = sitkRelabel.Execute(connected)

        print "make dictionary"
        # f dictionary
        lab_dict = {}
        print "f dict", f_dict
        for key in f_dict:
            print key
            print f_dict[key]
            lab_dict[key] = int(relabelled.GetPixel(*f_dict[key]))

        # This will change in refNode
        self.final_dict = lab_dict

        # If reference is given the label map should be ordered as per the reference
        if refNode:
            relabelled = self.reorderWithRef(relabelled, refNode, lab_dict)

        #turn sitk object into
        print "make slicer object"
        outputVolumeNode.LabelMapOn()
        nodeWriteAddress = sitkUtils.GetSlicerITKReadWriteAddress(outputVolumeNode.GetName())

        print "writing"
        sitk.WriteImage(relabelled, nodeWriteAddress)
        #self.makeSlicerObject(sitk_img = relabelled, name = outputVolumeNode.GetName(), label = True)

        print "Create color table"
        # make colour map based on the reference dict
        self.createColorTable(outputVolumeNode.GetName())

        slicer.modules.WaspWidget.progressHide()

        # This will make sure all queue items (dialog box and simpleitk stuff) will be removed.
        self.main_queue.put(self.main_queue_stop)

        return 0

    def createColorTable(self, outputVolumeNodeName):
        """ Creates a colour table with the names of the fiducials

        :param str outputVolumeNodeName:
        """
        # Need to use and reset WASP label if already their
        if slicer.util.getNode("WASP_labels"):
            color = slicer.util.getNode("WASP_labels")
            color.Reset()
        else:
            # Setup a new colour table
            color = slicer.vtkMRMLColorTableNode()
            color.SetNumberOfColors(3)
            color.SetName("WASP_labels")
            color.SetTypeToLabels()

        # Go through the self.final_dict instance attribute and set a new colour map using those names
        for name in self.final_dict:
            color.SetColorName(self.final_dict[name], name)

        # add to scene
        slicer.mrmlScene.AddNode(color)

        # print for check
        colorID = color.GetID()
        print outputVolumeNodeName
        print "colour", colorID

        # Setup the layers
        outputVolumeNode = slicer.util.getNode(str(outputVolumeNodeName))
        outputVolumeNode.SetDisplayVisibility(1)

        # Set to the output to show. Otherwise a volumeDisplayNode wont
        slicer.app.applicationLogic().GetSelectionNode().SetReferenceActiveVolumeID(outputVolumeNode.GetID())
        slicer.app.applicationLogic().PropagateVolumeSelection(0)

        display = outputVolumeNode.GetVolumeDisplayNode()
        display.SetAndObserveColorNodeID(str(colorID))


    def reorderWithRef(self, orginalLabelMap, refNode, lab_dict):
        """ This method reorders the label map into an order defined by simple text file.

        The text file should be created as follows: <label_map_number> tab <label_name>
        e.g. 1  liver
             2  lung

        :param obj orginalLabelMap: Original label map to be modified
        :param obj refNode: Node of the text file
        :param dict lab_dict: dictionary of the current label-organ setup
        """
        # Get the dictionary of the reference text file. The file is saved in slicer as a colour table
        print "\n\nGetting a dictionary for ref"
        ref_dict = {}
        ref_nm = refNode.GetNumberOfColors()

        # For loop to make a dictionary of ref labels
        for x in range(1, ref_nm):
            lab_nm = refNode.GetColorName(x).lower()
            ref_dict[lab_nm] = x

        print ref_dict

        # Now need to make a dictionary that simpleITK can use which will have the the original label map as the first
        # value and the label map it will change to as the second value e.g. 1  3
        #                                                                    2  5
        print "\n\nGetting a dictionary for sitk"
        sitk_dict = {}
        # Loop to make the dictionary for simpleITK
        for name in lab_dict:
            namelc = name.lower()
            if namelc in ref_dict:
                new_lb = ref_dict[namelc]
                sitk_dict[int(lab_dict[name])] = int(new_lb)
            else:
                ref_nm += 1
                sitk_dict[int(lab_dict[name])] = int(ref_nm)
                print "no standard label for " + str(name) + ". So assigned to " + str(ref_nm)
                # Add to the reference dictionary aswell
                ref_dict[namelc] = int(ref_nm)
                #print name+" Label_standard: "+str(label_standard[name])

        # Save as instance attribute
        self.final_dict = ref_dict

        # change label
        sitkChange = sitk.ChangeLabelImageFilter()
        sitkChange.SetChangeMap(sitk_dict)
        sitkChange = self.sitkProgress(sitkChange, "Change order")
        change = sitkChange.Execute(orginalLabelMap)
        return change

    def makeModel(self, outputVolumeNodeName, outputVolumeNode):
        """ Makes a model using the CLI 3D slicer model maker module

        :param str outputVolumeNodeName: Name of the label map to be made into a model
        :param obj outputVolumeNode: Node of the label map to made into a model
        :return:
        """
        print "make a model"
        slicer.modules.WaspWidget.updateStatusLabel("Make model")

        # Setup
        parameters = {}
        parameters['Name'] = outputVolumeNodeName
        parameters["InputVolume"] = outputVolumeNode.GetID()
        parameters['FilterType'] = "Sinc"
        parameters['GenerateAll'] = True
        parameters["JointSmoothing"] = False
        parameters["SplitNormals"] = True
        parameters["PointNormals"] = True
        parameters["SkipUnNamed"] = True
        parameters["Decimate"] = 0.25
        parameters["Smooth"] = 65

        # "add to scene" parameter
        self.outHierarchy = slicer.vtkMRMLModelHierarchyNode()
        self.outHierarchy.SetScene(slicer.mrmlScene)
        self.outHierarchy.SetName("WS Models")
        slicer.mrmlScene.AddNode(self.outHierarchy)
        parameters["ModelSceneFile"] = self.outHierarchy

        # Get an instance of the class
        modelMaker = slicer.modules.modelmaker

        #
        # run the task (in the background)
        # - use the GUI to provide progress feedback
        # - use the GUI's Logic to invoke the task
        # - model will show up when the processing is finished
        #
        slicer.modules.WaspWidget.updateStatusLabel("Making model")
        self.CLINode = slicer.cli.run(modelMaker, None, parameters)
        self.CLINode.AddObserver('ModifiedEvent', self.statusModel)
        print "done"
        return True

    def statusModel(self, caller, event):
        """ Listens to modelmaker module

        :param obj caller: Can get various info from the obj inculding the message
        :param event: ...not sure
        """
        if re.search("Completed", caller.GetStatusString()):

            slicer.modules.WaspWidget.updateStatusLabel("Done")
            slicer.modules.WaspWidget.progressHide()

            # End of WASP


    def gradientFilter(self, img):
        """ Peform the gradient filter

        :param obj img: simpleitk object
        :return SimpleITK filter object
        """
        slicer.modules.WaspWidget.updateStatusLabel("Performing gradient magnitude filter")
        slicer.modules.WaspWidget.progressShow()

        grad_filter = sitk.GradientMagnitudeRecursiveGaussianImageFilter()
        grad_filter.SetSigma(self.gradSig)
        grad_filter.SetNumberOfThreads(8)

        grad_filter = self.sitkProgress(grad_filter, "gradient")

        feature_img = grad_filter.Execute(img)

        slicer.modules.WaspWidget.progressHide()
        return feature_img

    def wsFilter(self, feature_img, ws_level):
        """ setup and perform watershed

        :param obj feature_img: SimpleITK object
        :param float ws_level: For watershed level parameter
        :return SimpleITK filter object
        """
        slicer.modules.WaspWidget.updateStatusLabel("Performing watershed " + str(ws_level))
        slicer.modules.WaspWidget.progressShow()
        name = "seg_ws_" + str(ws_level)
        print name
        ws_filter = sitk.MorphologicalWatershedImageFilter()
        ws_filter.SetLevel(float(ws_level))
        ws_filter.SetMarkWatershedLine(True)
        ws_filter.SetFullyConnected(False)
        ws_filter.SetNumberOfThreads(8)
        ws_filter = self.sitkProgress(ws_filter, "watershed")

        sitk_ws = ws_filter.Execute(feature_img)

        slicer.modules.WaspWidget.progressHide()
        return sitk_ws

    def relabelFilter(self, sitk_ws):
        """ Relabel the components in an object. Largest first. Filters out smaller components based on the
        parameter found in self.filterBy

        :param obj sitk_ws: SimpleITK object
        :return SimpleITK filter object
        """
        slicer.modules.WaspWidget.updateStatusLabel("Relabelling components")
        relabel_filter = sitk.RelabelComponentImageFilter()
        relabel_filter.SetMinimumObjectSize(int(self.filterBy))

        relabel_filter = self.sitkProgress(relabel_filter, "relabel")
        sitk_relabel = relabel_filter.Execute(sitk_ws)

        return sitk_relabel

    def makeSlicerObject(self, sitk_img, name, label):
        """ Make simpleITK object into slicer object

        :param obj sitk_img: SimpleITK image object
        :param str name: What the slicer object should be called
        :param bool label: True if label map. False if normal volume
        """
        # Get a slicer volume node ready
        slicer.modules.WaspWidget.updateStatusLabel("Converting sitk image into slicer object")
        slice_vol = slicer.vtkMRMLScalarVolumeNode()
        slice_vol.SetScene(slicer.mrmlScene)
        slice_vol.SetName(name)

        # check if it is to be a label map
        if label == True:
            slice_vol.LabelMapOn()

        # Add to scene
        slicer.mrmlScene.AddNode(slice_vol)

        # get the node address
        outputNodeName = slice_vol.GetName()
        nodeWriteAddress = sitkUtils.GetSlicerITKReadWriteAddress(outputNodeName)

        # simpleitk can now write to that node address
        sitk.WriteImage(sitk_img, nodeWriteAddress)

    def sitkProgress(self, sitk_object, name):
        """ Setup the simpleitk filter object so that it will update with progress

        :param obj sitk_object: SimpleITK filter object
        :param str name: Text which can be used to update GUI
        :return SimpleITK filter object
        """
        sitk_object.AddCommand(sitk.sitkProgressEvent, lambda: self.cmdProgressEvent(sitk_object, name))
        sitk_object.AddCommand(sitk.sitkStartEvent, lambda: self.cmdStartEvent(sitk_object))
        #sitk_object.AddCommand(sitk.sitkIterationEvent, lambda: self.cmdIterationEvent(sitk_object,nIter))
        sitk_object.AddCommand(sitk.sitkAbortEvent, lambda: self.cmdAbortEvent(sitk_object))
        sitk_object.AddCommand(sitk.sitkEndEvent, lambda: self.cmdEndEvent())
        return sitk_object

    def yieldPythonGIL(self, seconds=0):
        sleep(seconds)

    def cmdStartEvent(self, sitkFilter):
        #print "cmStartEvent"
        widget = slicer.modules.WaspWidget
        self.main_queue.put(lambda: widget.onLogicEventStart())
        self.yieldPythonGIL()

    def cmdCheckAbort(self, sitkFilter):
        if self.abort:
            sitkFilter.Abort()

    def cmdProgressEvent(self, sitkFilter, name):
        #print "cmProgressEvent", sitkFilter.GetProgress()
        self.main_queue.put(
            lambda p=sitkFilter.GetProgress(), n=name: slicer.modules.WaspWidget.onLogicEventProgress(p, n))
        self.cmdCheckAbort(sitkFilter)
        self.yieldPythonGIL()

    def cmdAbortEvent(self, sitkFilter):
        print "cmAbortEvent"
        widget = slicer.modules.WaspWidget
        self.main_queue.put(lambda: widget.onLogicEventAbort())
        self.yieldPythonGIL()

    def cmdEndEvent(self):
        widget = slicer.modules.WaspWidget
        self.main_queue.put(lambda: widget.onLogicEventEnd())
        self.yieldPythonGIL()

    def main_queue_start(self):
        """Begins monitoring of main_queue for callables"""
        self.main_queue_running = True
        #slicer.modules.WaspWidget.onLogicRunStart()
        qt.QTimer.singleShot(0, self.main_queue_process)

    def main_queue_stop(self):
        """End monitoring of main_queue for callables"""
        self.main_queue_running = False
        if self.thread.is_alive():
            self.thread.join()
            #slicer.modules.SimpleFiltersWidget.onLogicRunStop()

    def main_queue_process(self):
        """processes the main_queue of callables"""
        try:
            while not self.main_queue.empty():
                f = self.main_queue.get_nowait()
                if callable(f):
                    f()

            if self.main_queue_running:
                # Yield the GIL to allow other thread to do some python work.
                # This is needed since pyQt doesn't yield the python GIL
                self.yieldPythonGIL(.01)
                qt.QTimer.singleShot(0, self.main_queue_process)

        except Exception as e:
            #import sys
            sys.stderr.write("FilterLogic error in main_queue: \"{0}\"".format(e))

            # if there was an error try to resume
            if not self.main_queue.empty() or self.main_queue_running:
                qt.QTimer.singleShot(0, self.main_queue_process)


class WaspTest(unittest.TestCase):
    """
    This is the test case for your scripted module.
    """

    def delayDisplay(self, message, msec=1000):
        """This utility method displays a small dialog and waits.
      This does two things: 1) it lets the event loop catch up
      to the state of the test so that rendering and widget updates
      have all taken place before the test continues and 2) it
      shows the user/developer/tester the state of the test
      so that we'll know when it breaks.
      """
        print(message)
        self.info = qt.QDialog()
        self.infoLayout = qt.QVBoxLayout()
        self.info.setLayout(self.infoLayout)
        self.label = qt.QLabel(message, self.info)
        self.infoLayout.addWidget(self.label)
        qt.QTimer.singleShot(msec, self.info.close)
        self.info.exec_()

    def setUp(self):
        """ Do whatever is needed to reset the state - typically a scene clear will be enough.
        """
        slicer.mrmlScene.Clear(0)

    def runTest(self):
        """Run as few or as many tests as needed here.
      """
        self.setUp()
        self.test_test1()

    def test_test1(self):
        """ Ideally you should have several levels of tests.  At the lowest level
      tests sould exercise the functionality of the logic with different inputs
      (both valid and invalid).  At higher levels your tests should emulate the
      way the user would interact with your code and confirm that it still works
      the way you intended.
      One of the most important features of the tests is that it should alert other
      developers when their changes will have an impact on the behavior of your
      module.  For example, if a developer removes a feature that you depend on,
      your test should break so they know that the feature is needed.
      """

        self.delayDisplay("Starting the test")
        #
        #  first, get some data
        #
        import urllib

        downloads = (
            ('http://slicer.kitware.com/midas3/download?items=5767', 'FA.nrrd', slicer.util.loadVolume),
        )

        for url, name, loader in downloads:
            filePath = slicer.app.temporaryPath + '/' + name
            if not os.path.exists(filePath) or os.stat(filePath).st_size == 0:
                print('Requesting download %s from %s...\n' % (name, url))
                urllib.urlretrieve(url, filePath)
            if loader:
                print('Loading %s...\n' % (name,))
                loader(filePath)
                self.delayDisplay('Finished with download and loading\n')
                volumeNode = slicer.util.getNode(pattern="FA")
                logic = WaspLogic()
                self.delayDisplay('Image loading test')
                self.assertTrue(logic.hasImageData(volumeNode))
                self.delayDisplay('Test passed!')

                self.delayDisplay("logic test")
                logic.runWS(volumeNode,
                            1.2,
                            0.01,
                            0.01,
                            0.03,
                            10)
                self.delayDisplay('Test passed!')







