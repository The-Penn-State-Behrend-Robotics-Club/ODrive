import math
import can
from odrive_can import CANODrive
import time
import asyncio

bus = can.Bus("can0", bustype="socketcan")
axisID = 0x4


async def main():
    async with CANODrive.at(axisID, bus) as odrive:
        print(f"\nRequesting AXIS_STATE_FULL_CALIBRATION_SEQUENCE (0x03) on axisID: {axisID}")

        try:
            await odrive.set_axis_state(0x03)
            print(f"Message sent on {bus.channel_info}")
        except can.CanError as error:
            print("Message NOT sent!  Please verify can0 is working first")
            print(error)
            return

        print("Waiting for calibration to finish...")
        # Read messages infinitely and wait for the right ID to show up
        while await odrive.update_heartbeat():
            if odrive.axis_state == 0x01:
                print("\nAxis has returned to Idle state.")
                break

        if not odrive.connected:
            print("The ODrive was disconnected!")
            return

        if odrive.axis_error == 0x00:
            print("No errors")
        else:
            print("Axis error!  Error code: {hex(odrive.axis_error))}")
            return

        print(f"\nPutting axix {axisID} into AXIS_STATE_CLOSED_LOOP_CONTROL (0x08)...")

        try:
            await odrive.set_axis_state(0x08)
            print(f"Message sent on {bus.channel_info}")
        except can.CanError:
            print("Message NOT sent!")
            return

        while await odrive.update_heartbeat():
            print("\nReceived Axis heartbeat message")
            if odrive.axis_state == 0x8:
                print("Axis has entered closed loop")
            else:
                print("Axis failed to enter closed loop")
            break

        print(f"\nSetting axis {axisID}'s controller to CONTROL_MODE_POSITION_CONTROL (0x01)...")
        await odrive.set_controller_mode(0x01, input_mode=0x01)

        await odrive.set_limits(velocity_limit=10.0, current_limit=10.0)

        t0 = time.monotonic()
        while True:
            setpoint = 4.0 * math.sin((time.monotonic() - t0) * 2)
            print("goto " + str(setpoint))
            await odrive.set_input_pos(setpoint, vel_FF=0.0, torque_FF=0.0)
            await asyncio.sleep(0.01)

asyncio.run(main())
