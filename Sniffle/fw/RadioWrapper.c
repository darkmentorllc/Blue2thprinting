/*
 * Written by Sultan Qasim Khan
 * Copyright (c) 2016-2024, NCC Group plc
 * Released as open source under GPLv3
 */

/*********************************************************************
 * INCLUDES
 */
#include <errno.h>
#include <ti/sysbios/knl/Task.h>

// DriverLib
#include <ti/drivers/rf/RF.h>

#include "RFQueue.h"
#include "RadioWrapper.h"
#include "ti_radio_config.h"
#include "RadioTask.h"

#include DeviceFamily_constructPath(driverlib/rf_ble_mailbox.h)

/*********************************************************************
 * CONSTANTS
 */

/* TX Configuration: */
#define DATA_ENTRY_HEADER_SIZE 8    /* Constant header size of a Generic Data Entry */
#define MAX_LENGTH             257  /* Max 8-bit length + two byte BLE header */
#define NUM_DATA_ENTRIES       2    /* NOTE: Only two data entries supported at the moment */
#define NUM_APPENDED_BYTES     7    /* Appended RSSI, appended status word, appended 4 byte timestamp*/

/*********************************************************************
 * LOCAL VARIABLES
 */

static RF_Object bleRfObject;
static RF_Handle bleRfHandle;

/* Receive dataQueue for RF Core to fill in data */
static dataQueue_t dataQueue;

/* Buffer which contains all Data Entries for receiving data.
 * Pragmas are needed to make sure this buffer is 4 byte aligned (requirement from the RF Core) */
static uint8_t rxDataEntryBuffer [RF_QUEUE_DATA_ENTRY_BUFFER_SIZE(NUM_DATA_ENTRIES,
            MAX_LENGTH, NUM_APPENDED_BYTES)] __attribute__ ((aligned (4)));

static bool configured = false;
static bool ble4_cmd = false; // indicates one byte status word

static RadioWrapper_Callback userCallback = NULL;

/*********************************************************************
 * LOCAL FUNCTIONS
 */
static void rx_int_callback(RF_Handle h, RF_CmdHandle ch, RF_EventMask e);

/*********************************************************************
 * PUBLIC FUNCTIONS
 */

int RadioWrapper_init()
{
    if (!configured)
    {
        bleRfHandle = RF_open(&bleRfObject, &RF_prop,
                        (RF_RadioSetup*)&RF_cmdBle5RadioSetup, NULL);

        if(bleRfHandle < 0)
        {
            return -ENODEV;
        }

        if( RFQueue_defineQueue(&dataQueue,
                                rxDataEntryBuffer,
                                sizeof(rxDataEntryBuffer),
                                NUM_DATA_ENTRIES,
                                MAX_LENGTH + NUM_APPENDED_BYTES))
        {
            /* Failed to allocate space for all data entries */
            return -ENOMEM;
        }

        configured = true;
    }

    return 0;
}

// Sniff/Receive BLE packets
//
// Arguments:
//  phy         PHY mode to use
//  chan        Channel to listen on
//  accessAddr  BLE access address of packet to listen for
//  crcInit     Initial CRC value of packets being listened for
//  timeout     When to stop listening (in radio ticks)
//  forever     Ignore timeout and listen forever
//  validateCrc Discard packets with invalid CRC
//  callback    Function to call when a packet is received
//
// Returns:
//  Status code (errno.h), 0 on success
int RadioWrapper_recvFrames(PHY_Mode phy, uint32_t chan, uint32_t accessAddr,
    uint32_t crcInit, uint32_t timeout, bool forever, bool validateCrc,
    RadioWrapper_Callback callback)
{
    if ((!configured) || (chan >= 40))
        return -EINVAL;

    userCallback = callback;
    ble4_cmd = false;

    /* set up the receive request */
    RF_cmdBle5GenericRx.channel = chan;
    RF_cmdBle5GenericRx.whitening.init = 0x40 + chan;
    RF_cmdBle5GenericRx.phyMode.mainMode = (phy == PHY_CODED_S2) ? 2 : phy;
    RF_cmdBle5GenericRx.phyMode.coding = 0; // doesn't matter for receiver
    RF_cmdBle5GenericRx.pParams->pRxQ = &dataQueue;
    RF_cmdBle5GenericRx.pParams->accessAddress = accessAddr;
    RF_cmdBle5GenericRx.pParams->crcInit0 = crcInit & 0xFF;
    RF_cmdBle5GenericRx.pParams->crcInit1 = (crcInit >> 8) & 0xFF;
    RF_cmdBle5GenericRx.pParams->crcInit2 = (crcInit >> 16) & 0xFF;
    RF_cmdBle5GenericRx.pParams->bRepeat = 0x01; // receive multiple packets

    RF_cmdBle5GenericRx.pParams->rxConfig.bAutoFlushIgnored = 1;
    RF_cmdBle5GenericRx.pParams->rxConfig.bAutoFlushCrcErr = validateCrc ? 1 : 0;
    RF_cmdBle5GenericRx.pParams->rxConfig.bAutoFlushEmpty = 0;
    RF_cmdBle5GenericRx.pParams->rxConfig.bIncludeLenByte = 1;
    RF_cmdBle5GenericRx.pParams->rxConfig.bIncludeCrc = 0;
    RF_cmdBle5GenericRx.pParams->rxConfig.bAppendRssi = 1;
    RF_cmdBle5GenericRx.pParams->rxConfig.bAppendStatus = 1;
    RF_cmdBle5GenericRx.pParams->rxConfig.bAppendTimestamp = 1;

    if (forever)
    {
        RF_cmdBle5GenericRx.pParams->endTrigger.triggerType = TRIG_NEVER;
        RF_cmdBle5GenericRx.pParams->endTime = 0;
    } else {
        RF_cmdBle5GenericRx.pParams->endTrigger.triggerType = TRIG_ABSTIME;
        RF_cmdBle5GenericRx.pParams->endTime = timeout;
    }

    /* Enter RX mode and stay in RX till timeout */
    RF_runCmd(bleRfHandle, (RF_Op*)&RF_cmdBle5GenericRx, RF_PriorityNormal,
            &rx_int_callback, IRQ_RX_ENTRY_DONE);

    return 0;
}

/* sniff 37 -> wait for trigger -> wait 38 -> wait delay1 -> snif 39 -> wait delay2 -> done
 *
 * Notes on latency:
 * - Time from packet end transmitted to handling by software is around 150 us,
 *   though it varies, I've seen values from 128 to 168
 * - Time from triggering next channel to actually receiving on next channel is 160 us
 *   (sometimes it's better, as low as 100 us, but 160 is a good worst case value)
 * - The 160 us latency consists of the CMD_TRIGGER actually stopping the last operation,
 *   then tuning to next channel, and getting the radio ready to receive
 * - I don't know how much of the 160 us is ending the current operation vs preparing
 *   the next operation
 */
int RadioWrapper_recvAdv3(uint32_t delay1, uint32_t delay2, bool validateCrc,
        RadioWrapper_Callback callback)
{
    rfc_bleGenericRxPar_t para37;
    rfc_bleGenericRxPar_t para38;
    rfc_bleGenericRxPar_t para39;
    rfc_CMD_BLE5_GENERIC_RX_t sniff37;
    rfc_CMD_BLE5_GENERIC_RX_t sniff38;
    rfc_CMD_BLE5_GENERIC_RX_t sniff39;

    if (!configured)
        return -EINVAL;

    userCallback = callback;
    ble4_cmd = false;

    // commom parameters for sniffing advertisements
    para37.pRxQ = &dataQueue;
    para37.accessAddress = 0x8E89BED6;
    para37.crcInit0 = 0x55;
    para37.crcInit1 = 0x55;
    para37.crcInit2 = 0x55;
    para37.bRepeat = 0x01; // receive multiple packets
    para37.__dummy0 = 0x0000;
    para37.rxConfig.bAutoFlushIgnored = 1;
    para37.rxConfig.bAutoFlushCrcErr = validateCrc ? 1 : 0;
    para37.rxConfig.bAutoFlushEmpty = 0;
    para37.rxConfig.bIncludeLenByte = 1;
    para37.rxConfig.bIncludeCrc = 0;
    para37.rxConfig.bAppendRssi = 1;
    para37.rxConfig.bAppendStatus = 1;
    para37.rxConfig.bAppendTimestamp = 1;
    para37.endTrigger.triggerType = TRIG_NEVER;
    para37.endTrigger.bEnaCmd = 0;
    para37.endTrigger.triggerNo = 0x0;
    para37.endTrigger.pastTrig = 1;
    para37.endTime = 0;

    // set up the first generic RX struct
    sniff37.commandNo = 0x1829;
    sniff37.status = 0x0000;
    sniff37.pNextOp = NULL;
    sniff37.startTime = 0x00000000;
    sniff37.startTrigger.triggerType = TRIG_NOW;
    sniff37.startTrigger.bEnaCmd = 0;
    sniff37.startTrigger.triggerNo = 0x0;
    sniff37.startTrigger.pastTrig = 1;
    sniff37.condition.rule = COND_ALWAYS;
    sniff37.condition.nSkip = 0x0;
    sniff37.channel = 0;
    sniff37.whitening.init = 0x00;
    sniff37.whitening.bOverride = 0;
    sniff37.phyMode.mainMode = PHY_1M;
    sniff37.phyMode.coding = 0x0;
    sniff37.rangeDelay = 0x00;
    sniff37.txPower = 0x0000;
    sniff37.pParams = NULL;
    sniff37.pOutput = NULL;
    sniff37.tx20Power = 0x00000000;

    // duplicate the default settings
    para38 = para37;
    para39 = para37;
    sniff38 = sniff37;
    sniff39 = sniff37;

    // sniff 37, wait for trigger, sniff 38, sniff 39
    sniff37.pNextOp = delay1 > 0 ? (RF_Op *)&sniff38 : (RF_Op *)&sniff39;
    sniff37.pParams = &para37;
    sniff37.channel = 37;
    para37.endTrigger.triggerType = TRIG_NEVER;
    para37.endTrigger.bEnaCmd = 1;

    sniff38.pNextOp = (RF_Op *)&sniff39;
    sniff38.pParams = &para38;
    sniff38.channel = 38;
    para38.endTrigger.triggerType = TRIG_REL_PREVEND;
    para38.endTime = delay1;

    sniff39.pParams = &para39;
    sniff39.channel = 39;
    sniff39.condition.rule = COND_NEVER;
    para39.endTrigger.triggerType = TRIG_REL_PREVEND;
    para39.endTime = delay2;

    // run the command chain
    RF_runCmd(bleRfHandle, (RF_Op*)&sniff37, RF_PriorityNormal,
            &rx_int_callback, IRQ_RX_ENTRY_DONE);

    return 0;
}

void RadioWrapper_trigAdv3()
{
    // trigger switch from chan 37 to 38
    RF_runDirectCmd(bleRfHandle, 0x04040001);
}

/* Active Scanner
 *
 * Arguments:
 *  phy         PHY mode to use
 *  chan        Channel to listen on
 *  timeout     When to stop listening (in radio ticks)
 *  forever     Ignore timeout and listen forever
 *  scanAddr    Our (scanner) MAC address
 *  scanRandom  TxAdd of SCAN_REQ
 *  validateCrc Discard packets with invalid CRC
 *  callback    Function to call when a packet is received
 *
 * Returns:
 *  Status code (errno.h), 0 on success
 */
int RadioWrapper_scan(PHY_Mode phy, uint32_t chan, uint32_t timeout, bool forever,
        const uint16_t *scanAddr, bool scanRandom, bool validateCrc,
        RadioWrapper_Callback callback)
{

    if (!configured || chan < 37 || chan > 39)
        return -EINVAL;

    userCallback = callback;
    ble4_cmd = false;

    /* set up the receive request */
    RF_cmdBle5Scanner.channel = chan;
    RF_cmdBle5Scanner.whitening.init = 0x40 + chan;
    RF_cmdBle5Scanner.phyMode.mainMode = (phy == PHY_CODED_S2) ? 2 : phy;
    RF_cmdBle5Scanner.phyMode.coding = (phy == PHY_CODED_S2) ? 6 : 4;
    RF_cmdBle5Scanner.pParams->pRxQ = &dataQueue;

    RF_cmdBle5Scanner.pParams->scanConfig.scanFilterPolicy = 0; // scan everything
    RF_cmdBle5Scanner.pParams->scanConfig.bActiveScan = 1;
    RF_cmdBle5Scanner.pParams->scanConfig.deviceAddrType = scanRandom;
    RF_cmdBle5Scanner.pParams->scanConfig.rpaFilterPolicy = 1;
    RF_cmdBle5Scanner.pParams->scanConfig.bStrictLenFilter = 0;
    RF_cmdBle5Scanner.pParams->scanConfig.bAutoWlIgnore = 0;
    RF_cmdBle5Scanner.pParams->scanConfig.bEndOnRpt = 0;
    RF_cmdBle5Scanner.pParams->scanConfig.rpaMode = 0;
    RF_cmdBle5Scanner.pParams->scanConfig.rpaMode = 0;

    RF_cmdBle5Scanner.pParams->extFilterConfig.bCheckAdi = 0;
    RF_cmdBle5Scanner.pParams->extFilterConfig.bAutoAdiUpdate = 0;
    RF_cmdBle5Scanner.pParams->extFilterConfig.bApplyDuplicateFiltering = 0;
    RF_cmdBle5Scanner.pParams->extFilterConfig.bAutoWlIgnore = 0;

    RF_cmdBle5Scanner.pParams->randomState = 0; // radio will self-seed
    RF_cmdBle5Scanner.pParams->backoffCount = 1;
    RF_cmdBle5Scanner.pParams->backoffPar.logUpperLimit = 0;
    RF_cmdBle5Scanner.pParams->backoffPar.bLastSucceeded = 0;
    RF_cmdBle5Scanner.pParams->backoffPar.bLastFailed = 0;

    // Note: address pointers must be 16 bit aligned
    RF_cmdBle5Scanner.pParams->pDeviceAddress = (uint16_t *)scanAddr;
    RF_cmdBle5Scanner.pParams->pWhiteList = NULL;
    RF_cmdBle5Scanner.pParams->pAdiList = NULL;

    RF_cmdBle5Scanner.pParams->maxWaitTimeForAuxCh = 0xFFFF; // units?

    RF_cmdBle5Scanner.pParams->rxConfig.bAutoFlushIgnored = 1;
    RF_cmdBle5Scanner.pParams->rxConfig.bAutoFlushCrcErr = validateCrc ? 1 : 0;
    RF_cmdBle5Scanner.pParams->rxConfig.bAutoFlushEmpty = 0;
    RF_cmdBle5Scanner.pParams->rxConfig.bIncludeLenByte = 1;
    RF_cmdBle5Scanner.pParams->rxConfig.bIncludeCrc = 0;
    RF_cmdBle5Scanner.pParams->rxConfig.bAppendRssi = 1;
    RF_cmdBle5Scanner.pParams->rxConfig.bAppendStatus = 1;
    RF_cmdBle5Scanner.pParams->rxConfig.bAppendTimestamp = 1;

    if (forever)
    {
        RF_cmdBle5Scanner.pParams->endTrigger.triggerType = TRIG_NEVER;
        RF_cmdBle5Scanner.pParams->endTime = 0;
    } else {
        RF_cmdBle5Scanner.pParams->endTrigger.triggerType = TRIG_ABSTIME;
        RF_cmdBle5Scanner.pParams->endTime = timeout;
    }

    // always use endTrigger for timeout
    RF_cmdBle5Scanner.pParams->timeoutTrigger.triggerType = TRIG_NEVER;

    // Enter scanner mode and stay till timeout
    RF_runCmd(bleRfHandle, (RF_Op*)&RF_cmdBle5Scanner, RF_PriorityNormal,
            &rx_int_callback, IRQ_RX_ENTRY_DONE);

    return 0;
}

/* Active Scanner (Legacy Advertising Only)
 *
 * Arguments:
 *  chan        Channel to listen on
 *  timeout     When to stop listening (in radio ticks)
 *  forever     Ignore timeout and listen forever
 *  scanAddr    Our (scanner) MAC address
 *  scanRandom  TxAdd of SCAN_REQ
 *  validateCrc Discard packets with invalid CRC
 *  callback    Function to call when a packet is received
 *
 * Returns:
 *  Status code (errno.h), 0 on success
 */
int RadioWrapper_scanLegacy(uint32_t chan, uint32_t timeout, bool forever,
        const uint16_t *scanAddr, bool scanRandom, bool validateCrc,
        RadioWrapper_Callback callback)
{

    if (!configured || chan < 37 || chan > 39)
        return -EINVAL;

    userCallback = callback;
    ble4_cmd = true;

    /* set up the receive request */
    RF_cmdBleScanner.channel = chan;
    RF_cmdBleScanner.whitening.init = 0x40 + chan;
    RF_cmdBleScanner.pParams->pRxQ = &dataQueue;

    RF_cmdBleScanner.pParams->scanConfig.scanFilterPolicy = 0; // scan everything
    RF_cmdBleScanner.pParams->scanConfig.bActiveScan = 1;
    RF_cmdBleScanner.pParams->scanConfig.deviceAddrType = scanRandom;
    RF_cmdBleScanner.pParams->scanConfig.rpaFilterPolicy = 1;
    RF_cmdBleScanner.pParams->scanConfig.bStrictLenFilter = 0;
    RF_cmdBleScanner.pParams->scanConfig.bAutoWlIgnore = 0;
    RF_cmdBleScanner.pParams->scanConfig.bEndOnRpt = 0;
    RF_cmdBleScanner.pParams->scanConfig.rpaMode = 0;
    RF_cmdBleScanner.pParams->scanConfig.rpaMode = 0;

    RF_cmdBleScanner.pParams->randomState = 0; // radio will self-seed
    RF_cmdBleScanner.pParams->backoffCount = 1;
    RF_cmdBleScanner.pParams->backoffPar.logUpperLimit = 0;
    RF_cmdBleScanner.pParams->backoffPar.bLastSucceeded = 0;
    RF_cmdBleScanner.pParams->backoffPar.bLastFailed = 0;

    // Note: address pointers must be 16 bit aligned
    RF_cmdBleScanner.pParams->pDeviceAddress = (uint16_t *)scanAddr;
    RF_cmdBleScanner.pParams->pWhiteList = NULL;

    RF_cmdBleScanner.pParams->rxConfig.bAutoFlushIgnored = 1;
    RF_cmdBleScanner.pParams->rxConfig.bAutoFlushCrcErr = validateCrc ? 1 : 0;
    RF_cmdBleScanner.pParams->rxConfig.bAutoFlushEmpty = 0;
    RF_cmdBleScanner.pParams->rxConfig.bIncludeLenByte = 1;
    RF_cmdBleScanner.pParams->rxConfig.bIncludeCrc = 0;
    RF_cmdBleScanner.pParams->rxConfig.bAppendRssi = 1;
    RF_cmdBleScanner.pParams->rxConfig.bAppendStatus = 1;
    RF_cmdBleScanner.pParams->rxConfig.bAppendTimestamp = 1;

    if (forever)
    {
        RF_cmdBleScanner.pParams->endTrigger.triggerType = TRIG_NEVER;
        RF_cmdBleScanner.pParams->endTime = 0;
    } else {
        RF_cmdBleScanner.pParams->endTrigger.triggerType = TRIG_ABSTIME;
        RF_cmdBleScanner.pParams->endTime = timeout;
    }

    // always use endTrigger for timeout
    RF_cmdBleScanner.pParams->timeoutTrigger.triggerType = TRIG_NEVER;

    // Enter scanner mode and stay till timeout
    RF_runCmd(bleRfHandle, (RF_Op*)&RF_cmdBleScanner, RF_PriorityNormal,
            &rx_int_callback, IRQ_RX_ENTRY_DONE);

    return 0;
}

/* Transmit/receive in BLE5 Central Mode
 *
 * Arguments:
 *  phy         PHY mode to use
 *  chan        Channel to listen on
 *  accessAddr  BLE access address of packet to listen for
 *  crcInit     Initial CRC value of packets being listened for
 *  timeout     When to stop (in radio ticks)
 *  callback    Function to call when a packet is received
 *  txQueue     RF queue of packets to transmit
 *  startTime   When to start (in radio ticks), 0 for immediate
 *  numSent     Number of packets sent from txQueue written here
 *
 * Returns:
 *  Status code (errno.h), 0 on success
 */
int RadioWrapper_central(PHY_Mode phy, uint32_t chan, uint32_t accessAddr,
    uint32_t crcInit, uint32_t timeout, RadioWrapper_Callback callback,
    dataQueue_t *txQueue, uint32_t startTime, uint32_t *numSent)
{
    rfc_bleMasterSlaveOutput_t output = {};

    if ((!configured) || (chan >= 37))
        return -EINVAL;

    userCallback = callback;
    ble4_cmd = false;

    /* set up the send/receive request */
    RF_cmdBle5Master.channel = chan;
    RF_cmdBle5Master.whitening.init = 0x40 + chan;
    RF_cmdBle5Master.phyMode.mainMode = (phy == PHY_CODED_S2) ? 2 : phy;
    RF_cmdBle5Master.phyMode.coding = (phy == PHY_CODED_S2) ? 1 : 0;
    RF_cmdBle5Master.pOutput = &output;
    RF_cmdBle5Master.pParams->pRxQ = &dataQueue;
    RF_cmdBle5Master.pParams->pTxQ = txQueue;
    RF_cmdBle5Master.pParams->accessAddress = accessAddr;
    RF_cmdBle5Master.pParams->crcInit0 = crcInit & 0xFF;
    RF_cmdBle5Master.pParams->crcInit1 = (crcInit >> 8) & 0xFF;
    RF_cmdBle5Master.pParams->crcInit2 = (crcInit >> 16) & 0xFF;
    RF_cmdBle5Master.pParams->maxRxPktLen = 0xFF;

    // for the initiator -> central transition, we should reset seqStat there
    // we won't mess with seqStat here, just use the previous state

    RF_cmdBle5Master.pParams->rxConfig.bAutoFlushIgnored = 1;
    RF_cmdBle5Master.pParams->rxConfig.bAutoFlushCrcErr = 1;
    RF_cmdBle5Master.pParams->rxConfig.bAutoFlushEmpty = 0;
    RF_cmdBle5Master.pParams->rxConfig.bIncludeLenByte = 1;
    RF_cmdBle5Master.pParams->rxConfig.bIncludeCrc = 0;
    RF_cmdBle5Master.pParams->rxConfig.bAppendRssi = 1;
    RF_cmdBle5Master.pParams->rxConfig.bAppendStatus = 1;
    RF_cmdBle5Master.pParams->rxConfig.bAppendTimestamp = 1;

    // start immediately if startTime = 0
    if (startTime == 0)
    {
        RF_cmdBle5Master.startTrigger.triggerType = TRIG_NOW;
    } else {
        RF_cmdBle5Master.startTrigger.triggerType = TRIG_ABSTIME;
        RF_cmdBle5Master.startTrigger.pastTrig = 1;
        RF_cmdBle5Master.startTime = startTime;
    }

    RF_cmdBle5Master.pParams->endTrigger.triggerType = TRIG_ABSTIME;
    RF_cmdBle5Master.pParams->endTime = timeout;

    /* Enter central mode, and stay till we're done */
    RF_runCmd(bleRfHandle, (RF_Op*)&RF_cmdBle5Master, RF_PriorityNormal,
            &rx_int_callback, IRQ_RX_ENTRY_DONE);

    *numSent = output.nTxEntryDone;

    switch (RF_cmdBle5Master.status)
    {
    case BLE_DONE_OK:
    case BLE_DONE_ENDED:
    case BLE_DONE_STOPPED:
        return 0;
    default:
        return -ENOLINK;
    }
}

/* Receive/transmit in BLE5 Peripheral Mode
 *
 * Arguments:
 *  phy         PHY mode to use
 *  chan        Channel to listen on
 *  accessAddr  BLE access address of packet to listen for
 *  crcInit     Initial CRC value of packets being listened for
 *  timeout     When to stop (in radio ticks)
 *  callback    Function to call when a packet is received
 *  txQueue     RF queue of packets to transmit
 *  startTime   When to start (in radio ticks), 0 for immediate
 *  numSent     Number of packets sent from txQueue written here
 *
 * Returns:
 *  Status code (errno.h), 0 on success
 */
int RadioWrapper_peripheral(PHY_Mode phy, uint32_t chan, uint32_t accessAddr,
    uint32_t crcInit, uint32_t timeout, RadioWrapper_Callback callback,
    dataQueue_t *txQueue, uint32_t startTime, uint32_t *numSent)
{
    rfc_bleMasterSlaveOutput_t output = {};

    if ((!configured) || (chan >= 37))
        return -EINVAL;

    userCallback = callback;
    ble4_cmd = false;

    /* set up the send/receive request */
    RF_cmdBle5Slave.channel = chan;
    RF_cmdBle5Slave.whitening.init = 0x40 + chan;
    RF_cmdBle5Slave.phyMode.mainMode = (phy == PHY_CODED_S2) ? 2 : phy;
    RF_cmdBle5Slave.phyMode.coding = (phy == PHY_CODED_S2) ? 1 : 0;
    RF_cmdBle5Slave.pOutput = &output;
    RF_cmdBle5Slave.pParams->pRxQ = &dataQueue;
    RF_cmdBle5Slave.pParams->pTxQ = txQueue;
    RF_cmdBle5Slave.pParams->accessAddress = accessAddr;
    RF_cmdBle5Slave.pParams->crcInit0 = crcInit & 0xFF;
    RF_cmdBle5Slave.pParams->crcInit1 = (crcInit >> 8) & 0xFF;
    RF_cmdBle5Slave.pParams->crcInit2 = (crcInit >> 16) & 0xFF;
    RF_cmdBle5Slave.pParams->maxRxPktLen = 0xFF;

    // for the advertiser -> peripheral transition, we should reset seqStat there
    // we won't mess with seqStat here, just use the previous state

    RF_cmdBle5Slave.pParams->rxConfig.bAutoFlushIgnored = 1;
    RF_cmdBle5Slave.pParams->rxConfig.bAutoFlushCrcErr = 1;
    RF_cmdBle5Slave.pParams->rxConfig.bAutoFlushEmpty = 0;
    RF_cmdBle5Slave.pParams->rxConfig.bIncludeLenByte = 1;
    RF_cmdBle5Slave.pParams->rxConfig.bIncludeCrc = 0;
    RF_cmdBle5Slave.pParams->rxConfig.bAppendRssi = 1;
    RF_cmdBle5Slave.pParams->rxConfig.bAppendStatus = 1;
    RF_cmdBle5Slave.pParams->rxConfig.bAppendTimestamp = 1;

    // start immediately if startTime = 0
    if (startTime == 0)
    {
        RF_cmdBle5Slave.startTrigger.triggerType = TRIG_NOW;
    } else {
        RF_cmdBle5Slave.startTrigger.triggerType = TRIG_ABSTIME;
        RF_cmdBle5Slave.startTrigger.pastTrig = 1;
        RF_cmdBle5Slave.startTime = startTime;
    }

    // endTrigger is for after C->P is received
    // timeoutTrigger is for before C->P is received
    // both triggers need to be set for reliability
    RF_cmdBle5Slave.pParams->endTrigger.triggerType = TRIG_ABSTIME;
    RF_cmdBle5Slave.pParams->endTime = timeout;
    RF_cmdBle5Slave.pParams->timeoutTrigger.triggerType = TRIG_ABSTIME;
    RF_cmdBle5Slave.pParams->timeoutTime = timeout;

    /* Enter peripheral mode, and stay till we're done */
    RF_runCmd(bleRfHandle, (RF_Op*)&RF_cmdBle5Slave, RF_PriorityNormal,
            &rx_int_callback, IRQ_RX_ENTRY_DONE);

    *numSent = output.nTxEntryDone;

    switch (RF_cmdBle5Slave.status)
    {
    case BLE_DONE_OK:
    case BLE_DONE_ENDED:
    case BLE_DONE_STOPPED:
        return 0;
    default:
        return -ENOLINK;
    }
}

void RadioWrapper_resetSeqStat()
{
    RF_cmdBle5Master.pParams->seqStat.lastRxSn = 1;
    RF_cmdBle5Master.pParams->seqStat.lastTxSn = 1;
    RF_cmdBle5Master.pParams->seqStat.nextTxSn = 0;
    RF_cmdBle5Master.pParams->seqStat.bFirstPkt = 1;
    RF_cmdBle5Master.pParams->seqStat.bAutoEmpty = 0;
    RF_cmdBle5Master.pParams->seqStat.bLlCtrlTx = 0;
    RF_cmdBle5Master.pParams->seqStat.bLlCtrlAckRx = 0;
    RF_cmdBle5Master.pParams->seqStat.bLlCtrlAckPending = 0;
    RF_cmdBle5Slave.pParams->seqStat.lastRxSn = 1;
    RF_cmdBle5Slave.pParams->seqStat.lastTxSn = 1;
    RF_cmdBle5Slave.pParams->seqStat.nextTxSn = 0;
    RF_cmdBle5Slave.pParams->seqStat.bFirstPkt = 1;
    RF_cmdBle5Slave.pParams->seqStat.bAutoEmpty = 0;
    RF_cmdBle5Slave.pParams->seqStat.bLlCtrlTx = 0;
    RF_cmdBle5Slave.pParams->seqStat.bLlCtrlAckRx = 0;
    RF_cmdBle5Slave.pParams->seqStat.bLlCtrlAckPending = 0;
}

/* Initiate a connection to the specified peer address
 *
 * Arguments:
 *  phy         PHY mode to use (primary adv.)
 *  chan        Channel to listen on (primary adv.)
 *  timeout     When to stop (in radio ticks)
 *  forever     Ignore timeout and listen forever
 *  callback    Function to call when a packet is received
 *  initAddr    Our (initiator) MAC address
 *  initRandom  TxAdd of CONNECT_IND
 *  peerAddr    Peer (advertiser) MAC address
 *  peerRandom  RxAdd of CONNECT_IND
 *  connReqData LLData of CONNECT_IND
 *  connTime    Time of first connection event is written here
 *  connPhy     PHY used for connection is written here
 *
 * Returns:
 *  -3 on misc error
 *  -2 on connection failure (no AUX_CONNECT_RSP)
 *  -1 on timeout (didn't get connectable peer advert)
 *  0 on legacy connection success with ChSel0
 *  1 on legacy connection success with ChSel1
 *  2 on aux connection success (implies ChSel1)
 */
int RadioWrapper_initiate(PHY_Mode phy, uint32_t chan, uint32_t timeout, bool forever,
    RadioWrapper_Callback callback, const uint16_t *initAddr, bool initRandom,
    const uint16_t *peerAddr, bool peerRandom, const void *connReqData,
    uint32_t *connTime, PHY_Mode *connPhy)
{
    if (!configured)
        return -EINVAL;

    userCallback = callback;
    ble4_cmd = false;

    // set up initiator parameters
    RF_cmdBle5Initiator.channel = chan;
    RF_cmdBle5Initiator.whitening.init = 0x40 + chan;
    RF_cmdBle5Initiator.phyMode.mainMode = (phy == PHY_CODED_S2) ? 2 : phy;
    RF_cmdBle5Initiator.phyMode.coding = (phy == PHY_CODED_S2) ? 6 : 4;
    RF_cmdBle5Initiator.pParams->pRxQ = &dataQueue;

    RF_cmdBle5Initiator.pParams->rxConfig.bAutoFlushIgnored = 1;
    RF_cmdBle5Initiator.pParams->rxConfig.bAutoFlushCrcErr = 1;
    RF_cmdBle5Initiator.pParams->rxConfig.bAutoFlushEmpty = 0;
    RF_cmdBle5Initiator.pParams->rxConfig.bIncludeLenByte = 1;
    RF_cmdBle5Initiator.pParams->rxConfig.bIncludeCrc = 0;
    RF_cmdBle5Initiator.pParams->rxConfig.bAppendRssi = 1;
    RF_cmdBle5Initiator.pParams->rxConfig.bAppendStatus = 1;
    RF_cmdBle5Initiator.pParams->rxConfig.bAppendTimestamp = 1;

    RF_cmdBle5Initiator.pParams->initConfig.bUseWhiteList = 0; // specific peer
    RF_cmdBle5Initiator.pParams->initConfig.bDynamicWinOffset = 1;
    RF_cmdBle5Initiator.pParams->initConfig.deviceAddrType = initRandom ? 1 : 0;
    RF_cmdBle5Initiator.pParams->initConfig.peerAddrType = peerRandom ? 1 : 0;
    RF_cmdBle5Initiator.pParams->initConfig.bStrictLenFilter = 1;
    RF_cmdBle5Initiator.pParams->initConfig.chSel = 1; // we can use CSA2

    RF_cmdBle5Initiator.pParams->randomState = 0;
    // TODO: should I touch backoff parameters here?

    RF_cmdBle5Initiator.pParams->connectReqLen = 22; // as per BLE spec
    RF_cmdBle5Initiator.pParams->pConnectReqData = (uint8_t *)connReqData;

    // Note: these pointers must be 16 bit aligned
    // According to docs, pWhiteList can be overridden as peer address
    RF_cmdBle5Initiator.pParams->pDeviceAddress = (uint16_t *)initAddr;
    RF_cmdBle5Initiator.pParams->pWhiteList = (rfc_bleWhiteListEntry_t *)peerAddr;

    RF_cmdBle5Initiator.pParams->connectTime = RF_getCurrentTime() + 4000;
    RF_cmdBle5Initiator.pParams->maxWaitTimeForAuxCh = 0xFFFF; // units?

    if (forever)
    {
        RF_cmdBle5Initiator.pParams->endTrigger.triggerType = TRIG_NEVER;
        RF_cmdBle5Initiator.pParams->endTime = 0;
    } else {
        RF_cmdBle5Initiator.pParams->endTrigger.triggerType = TRIG_ABSTIME;
        RF_cmdBle5Initiator.pParams->endTime = timeout;
    }

    /* for now, we're not defining a timeout separate from end */
    RF_cmdBle5Initiator.pParams->timeoutTrigger.triggerType = TRIG_NEVER;
    RF_cmdBle5Initiator.pParams->timeoutTime = 0;

    /* Enter initiator mode, and stay till we're done */
    RF_runCmd(bleRfHandle, (RF_Op*)&RF_cmdBle5Initiator, RF_PriorityNormal,
            &rx_int_callback, IRQ_RX_ENTRY_DONE);

    *connTime = RF_cmdBle5Initiator.pParams->connectTime;

    if (RF_cmdBle5Initiator.status == BLE_DONE_CONNECT_CHSEL0)
        *connPhy = PHY_1M;
    else if (RF_cmdBle5Initiator.pParams->rxListenTime == 0) // no aux pkt received
        *connPhy = PHY_1M;
    else
        *connPhy = (PHY_Mode)RF_cmdBle5Initiator.pParams->phyMode;

    switch (RF_cmdBle5Initiator.status)
    {
    case BLE_DONE_CONNECT:
    if (RF_cmdBle5Initiator.pParams->rxListenTime != 0) // aux pkt received
        return 2;
    else
        return 1;
    case BLE_DONE_CONNECT_CHSEL0:
        return 0;
    case BLE_DONE_RXTIMEOUT:
    case BLE_DONE_ENDED:
    case BLE_DONE_STOPPED:
        return -1;
    case BLE_DONE_NOSYNC:
        return -2;
    default:
        return -3;
    }
}

/* Advertises in legacy mode on 37/38/39, accepts connections
 *
 * Arguments:
 *  callback    Function to call when a packet is received
 *  advAddr     Our (advertiser) MAC address
 *  advRandom   TxAdd for advertisement
 *  advData     Advertisement data
 *  advLen      Advertisement data length
 *  scanRspData Scan response data
 *  scanRspLen  Scan response data length
 *  mode        Advertisement type
 *
 * Returns:
 *  -1 if no connection request or error
 *  0 on legacy connection success with ChSel0
 *  1 on legacy connection success with ChSel1
 */
int RadioWrapper_advertise3(RadioWrapper_Callback callback, const uint16_t *advAddr,
    bool advRandom, const void *advData, uint8_t advLen, const void *scanRspData,
    uint8_t scanRspLen, ADV_Mode mode)
{
    rfc_bleAdvPar_t params;
    rfc_CMD_BLE_ADV_t adv37;
    rfc_CMD_BLE_ADV_t adv38;
    rfc_CMD_BLE_ADV_t adv39;

    if (!configured)
        return -EINVAL;

    userCallback = callback;
    ble4_cmd = true;

    memset(&adv37, 0, sizeof(adv37));

    switch (mode)
    {
    case LEGACY_CONNECTABLE:
        adv37.commandNo = 0x1803;
        break;
    case LEGACY_NON_CONNECTABLE:
        adv37.commandNo = 0x1805;
        break;
    case LEGACY_SCANNABLE:
        adv37.commandNo = 0x1806;
        break;
    default:
        // LEGACY_DIRECT not supported for now
        return -EINVAL;
    }

    adv37.condition.rule = COND_STOP_ON_FALSE;
    adv37.pParams = &params;

    memset(&params, 0, sizeof(params));
    params.pRxQ = &dataQueue;
    params.rxConfig.bAutoFlushIgnored = 1;
    params.rxConfig.bAutoFlushCrcErr = 1;
    params.rxConfig.bAutoFlushEmpty = 0;
    params.rxConfig.bIncludeLenByte = 1;
    params.rxConfig.bIncludeCrc = 0;
    params.rxConfig.bAppendRssi = 1;
    params.rxConfig.bAppendStatus = 1;
    params.rxConfig.bAppendTimestamp = 1;

    params.advConfig.advFilterPolicy = 0x0; // no whitelist
    params.advConfig.deviceAddrType = advRandom ? 1 : 0;
    params.advConfig.peerAddrType = 0; // not applicable
    params.advConfig.bStrictLenFilter = 0;
    params.advConfig.chSel = 1; // allow CSA 2
    params.advConfig.privIgnMode = 0; // ???
    params.advConfig.rpaMode = 0;

    params.advLen = advLen;
    params.scanRspLen = scanRspLen;
    params.pAdvData = (void *)advData;
    params.pScanRspData = (void *)scanRspData;
    params.pDeviceAddress = (uint16_t *)advAddr;

    // will end automatically when done, no need for timed trigger
    params.endTrigger.triggerType = TRIG_NEVER;

    // duplicate the common settings
    adv38 = adv37;
    adv39 = adv37;

    // set up chain of advertising on 37, 38, 39
    adv37.pNextOp = (RF_Op *)&adv38;
    adv37.channel = 37;
    adv38.pNextOp = (RF_Op *)&adv39;
    adv38.channel = 38;
    adv39.channel = 39;
    adv39.condition.rule = COND_NEVER;

    /* Enter advertiser mode, and stay till we're done */
    RF_runCmd(bleRfHandle, (RF_Op*)&adv37, RF_PriorityNormal,
            &rx_int_callback, IRQ_RX_ENTRY_DONE);

    if (adv37.status == BLE_DONE_CONNECT ||
            adv38.status == BLE_DONE_CONNECT ||
            adv39.status == BLE_DONE_CONNECT)
        return 1;
    else if (adv37.status == BLE_DONE_CONNECT_CHSEL0 ||
            adv38.status == BLE_DONE_CONNECT_CHSEL0 ||
            adv39.status == BLE_DONE_CONNECT_CHSEL0)
        return 0;
    else
        return -1;
}

/* Advertises in extended mode on 37/38/39 and secondary channel
 *
 * Arguments:
 *  callback        Function to call when a packet is received
 *  advAddr         Our (advertiser) MAC address
 *  advRandom       TxAdd for advertisement
 *  advData         Advertisement data
 *  advLen          Advertisement data length
 *  mode            Advertisement type
 *  primaryPhy      Primary channel PHY
 *  secondaryPhy    Secondary channel PHY
 *  secondaryChan   Secondary channel number
 *  adi             AdvDataInfo field
 *
 * Returns:
 *  -1 if no connection request or error
 *  0 on extended connection request
 */
int RadioWrapper_advertiseExt3(RadioWrapper_Callback callback, const uint16_t *advAddr,
    bool advRandom, const void *advData, uint8_t advLen, ADV_EXT_Mode mode,
    PHY_Mode primaryPhy, PHY_Mode secondaryPhy, uint32_t secondaryChan, uint16_t adi)
{
    rfc_ble5AdvExtPar_t params;
    rfc_ble5AdvAuxPar_t params2;
    rfc_ble5ExtAdvEntry_t advPkt;
    rfc_ble5ExtAdvEntry_t advPkt2;
    rfc_ble5ExtAdvEntry_t advPkt3;
    rfc_CMD_BLE5_ADV_EXT_t adv37;
    rfc_CMD_BLE5_ADV_EXT_t adv38;
    rfc_CMD_BLE5_ADV_EXT_t adv39;
    rfc_CMD_BLE5_ADV_AUX_t adv2;
    uint8_t extHdr[5] = {}; // ADI and AuxPtr

    if (!configured ||
            primaryPhy == PHY_2M ||
            secondaryChan > 36 ||
            mode > EXT_SCANNABLE)
        return -EINVAL;

    userCallback = callback;
    ble4_cmd = false;

    // Set up primary channel advertising
    memset(&adv37, 0, sizeof(adv37));
    adv37.commandNo = 0x1823;
    adv37.condition.rule = COND_STOP_ON_FALSE;
    adv37.phyMode.mainMode = (primaryPhy == PHY_CODED_S2) ? 2 : primaryPhy;
    adv37.phyMode.coding = (primaryPhy == PHY_CODED_S2) ? 7 : 4;
    adv37.pParams = &params;

    memset(&params, 0, sizeof(params));
    params.advConfig.deviceAddrType = advRandom ? 1 : 0;
    params.auxPtrTargetType = TRIG_ABSTIME;
    if (primaryPhy == PHY_1M)
        params.auxPtrTargetTime = RF_getCurrentTime() + 2*4000;
    else if (primaryPhy == PHY_CODED_S8)
        params.auxPtrTargetTime = RF_getCurrentTime() + 5*4000;
    else // PHY_CODED_S2
        params.auxPtrTargetTime = RF_getCurrentTime() + 3*4000;
    params.pAdvPkt = (uint8_t *)&advPkt;
    params.pDeviceAddress = (uint16_t *)advAddr;

    memset(&advPkt, 0, sizeof(advPkt));
    advPkt.extHdrInfo.length = 6;
    advPkt.extHdrInfo.advMode = mode;
    advPkt.extHdrFlags = 0x18; // ADI and AuxPtr
    advPkt.pExtHeader = extHdr;

    memcpy(extHdr, &adi, sizeof(adi));
    extHdr[2] = secondaryChan | 0x40;
    extHdr[4] = (secondaryPhy == PHY_CODED_S2) ? 2 << 5 : secondaryPhy << 5;

    // Duplicate the common settings
    adv38 = adv37;
    adv39 = adv37;

    // Set up chain of advertising on 37, 38, 39, secondary
    adv37.pNextOp = (RF_Op *)&adv38;
    adv37.channel = 37;
    adv38.pNextOp = (RF_Op *)&adv39;
    adv38.channel = 38;
    adv39.pNextOp = (RF_Op *)&adv2;
    adv39.channel = 39;

    // Set up secondary channel advertising
    memset(&adv2, 0, sizeof(adv2));
    adv2.commandNo = 0x1824;
    adv2.startTime = params.auxPtrTargetTime;
    adv2.startTrigger.triggerType = TRIG_ABSTIME;
    adv2.startTrigger.pastTrig = 1;
    adv2.condition.rule = COND_NEVER;
    adv2.channel = secondaryChan;
    adv2.phyMode.mainMode = (secondaryPhy == PHY_CODED_S2) ? 2 : secondaryPhy;
    adv2.phyMode.coding = (secondaryPhy == PHY_CODED_S2) ? 7 : 4;
    adv2.pParams = &params2;

    memset(&params2, 0, sizeof(params2));
    params2.pRxQ = &dataQueue;
    params2.rxConfig.bAutoFlushIgnored = 1;
    params2.rxConfig.bAutoFlushCrcErr = 1;
    params2.rxConfig.bAutoFlushEmpty = 0;
    params2.rxConfig.bIncludeLenByte = 1;
    params2.rxConfig.bIncludeCrc = 0;
    params2.rxConfig.bAppendRssi = 1;
    params2.rxConfig.bAppendStatus = 1;
    params2.rxConfig.bAppendTimestamp = 1;

    params2.advConfig.advFilterPolicy = 0x0; // no whitelist
    params2.advConfig.deviceAddrType = advRandom ? 1 : 0;
    params2.advConfig.targetAddrType = 0; // not applicable
    params2.advConfig.bStrictLenFilter = 0;
    params2.advConfig.bDirected = 0;
    params2.advConfig.rpaMode = 0;

    params2.pAdvPkt = (uint8_t *)&advPkt2;
    params2.pRspPkt = (uint8_t *)&advPkt3;
    params2.pDeviceAddress = (uint16_t *)advAddr;

    // AUX_ADV_IND
    memset(&advPkt2, 0, sizeof(advPkt2));
    advPkt2.extHdrInfo.length = 9;
    advPkt2.extHdrInfo.advMode = mode;
    advPkt2.extHdrFlags = 0x09; // AdvA and ADI
    advPkt2.extHdrConfig.bSkipAdvA = 1;
    advPkt2.pExtHeader = extHdr;
    if (mode != EXT_SCANNABLE)
    {
        advPkt2.advDataLen = advLen;
        advPkt2.pAdvData = (uint8_t *)advData;
    }

    memset(&advPkt3, 0, sizeof(advPkt3));
    if (mode == EXT_CONNECTABLE) {
        // AUX_CONNECT_RSP
        advPkt3.extHdrInfo.length = 13;
        advPkt3.extHdrInfo.advMode = 0;
        advPkt3.extHdrFlags = 0x03; // AdvA and TargetA
        advPkt3.extHdrConfig.bSkipAdvA = 1;
        advPkt3.extHdrConfig.bSkipTargetA = 1;
    } else if (mode == EXT_SCANNABLE) {
        // AUX_SCAN_RSP
        advPkt3.extHdrInfo.length = 9;
        advPkt3.extHdrInfo.advMode = 0;
        advPkt3.extHdrFlags = 0x09; // AdvA and ADI
        advPkt3.extHdrConfig.bSkipAdvA = 1;
        advPkt3.pExtHeader = extHdr;
        advPkt3.advDataLen = advLen;
        advPkt3.pAdvData = (uint8_t *)advData;
    }

    // Enter advertiser mode, and stay till we're done
    RF_runCmd(bleRfHandle, (RF_Op*)&adv37, RF_PriorityNormal,
            &rx_int_callback, IRQ_RX_ENTRY_DONE);

    return adv2.status == BLE_DONE_CONNECT ? 0 : -1;
}

void RadioWrapper_setTxPower(int8_t power)
{
    RF_TxPowerTable_Value value = txPowerTable[TX_POWER_TABLE_SIZE - 1].value;
    int i;

    for (i = 0; i < TX_POWER_TABLE_SIZE; i++)
    {
        if (txPowerTable[i].power >= power)
        {
            value = txPowerTable[i].value;
            break;
        }
    }

    RF_setTxPower(bleRfHandle, value);
}

void RadioWrapper_stop()
{
    // Gracefully stop any radio operations
    RF_runDirectCmd(bleRfHandle, 0x04020001);
}

static void rx_int_callback(RF_Handle h, RF_CmdHandle ch, RF_EventMask e)
{
    BLE_Frame frame;
    rfc_dataEntryGeneral_t *currentDataEntry;
    uint8_t *packetPointer;

    if (e & RF_EventRxEntryDone)
    {
        /* Get current unhandled data entry */
        currentDataEntry = RFQueue_getDataEntry();
        packetPointer = (uint8_t *)(&currentDataEntry->data);

        /* In the current radio configuration:
         * Byte 0:      Advertisement/data PDU header
         * Byte 1:      PDU body length (advert or data)
         * Byte 2...:   PDU body
         * Byte 2+l:    RSSI
         * Byte 3+l:    Channel (and bIgnore, bCrcErr)
         * Byte 4+l:    PHY mode (byte not present if ble4_cmd)
         * Byte 5+l...: Timestamp (32 bit)
         */
        frame.length = packetPointer[1] + 2;
        frame.pData = packetPointer;

        frame.rssi = (int8_t)packetPointer[frame.length];
        frame.channel = packetPointer[frame.length + 1] & 0x3F;
        frame.crcError = (packetPointer[frame.length + 1] & 0x80) ? 1 : 0;

        if (ble4_cmd)
        {
            frame.phy = PHY_1M;
            memcpy(&frame.timestamp, packetPointer + frame.length + 2, 4);
        } else {
            frame.phy = packetPointer[frame.length + 2] & 0x3;
            memcpy(&frame.timestamp, packetPointer + frame.length + 3, 4);
        }

        /* gets overwritten with actual value in user callback */
        frame.direction = 0;
        frame.eventCtr = 0;

        if (userCallback) userCallback(&frame);

        RFQueue_nextEntry();
    }
}

int RadioWrapper_close()
{
    if (!configured)
        return -EINVAL;

    RF_close(bleRfHandle);

    configured = false;

    return 0;
}
