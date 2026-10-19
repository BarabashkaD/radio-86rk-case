"""Canonical accepted v10 dimensions. All units mm except angles in degrees.
Integration helpers must consume this configuration rather than infer slot height
from an obsolete seam. This module alone does not claim a full rebuilt model.
"""
from dataclasses import dataclass,asdict
import math
PCB_MOUNTS=((11.43,-11.43),(267.97,-11.43),(11.43,-91.44),(267.97,-91.44),(139.7,-110.49),(62.23,-204.47),(207.01,-204.47))
CASE_MOUNTS=((-1.8,-198.),(-1.8,-24.),(281.2,-198.),(281.2,-24.))
FEET_AXES=((40.,-35.,2.5),(239.4,-35.,2.5))
@dataclass(frozen=True)
class Parameters:
 Width:float=300.;Depth:float=215.95;CenterX:float=139.7
 Floor:float=3.;Wall:float=2.8;OuterCornerRadius:float=5.
 PCBThickness:float=1.6;PCBBottomZ:float=13.
 ShoulderZ:float=30.;RoofZ:float=37.5;DeckZ:float=20.6
 SideSeamZ:float=16.2;RearSeamZ:float=21.6;RearRampLength:float=20.
 TongueWidth:float=1.2;TongueHeight:float=2.;GrooveWidth:float=1.5;GrooveHeight:float=2.3
 JointGap:float=.3;JointLargeRadius:float=.6;JointSmallRadius:float=.3;OuterSeamChamfer:float=.3
 SideSlotExternalWidth:float=3.;SideSlotAngle:float=60.;SideSlotPitch:float=5.5;SideSlotHeight:float=6.;SideSlotBottomMargin:float=5.
 TopSlotExternalWidth:float=3.;TopSlotLength:float=18.;TopSlotAngle:float=60.;TopSlotPitch:float=5.5
 RibWidth:float=1.8;RibHeight:float=6.;FloorInnerRadius:float=2.;RibRootRadius:float=.6;RibNodeRadius:float=1.;PostRootRadius:float=2.
 BossDiameter:float=10.;CaseSeatZ:float=16.2;ScrewLength:float=20.;HeadSeatZ:float=3.2;HeadPocketDiameter:float=6.6;CaseThroughDiameter:float=3.4
 InsertLength:float=5.7;InsertOD:float=4.6;PilotDiameter:float=4.;CapEdgeZ:float=23.2;CapRise:float=.2
 @property
 def SideSlotTopMargin(self):return self.SideSeamZ-self.SideSlotBottomMargin-self.SideSlotHeight
 @property
 def PCBTopZ(self):return self.PCBBottomZ+self.PCBThickness
 @property
 def CapRadius(self):return ((self.PilotDiameter/2)**2+self.CapRise**2)/(2*self.CapRise)
 @property
 def CapApexZ(self):return self.CapEdgeZ+self.CapRise
 def validate(self):
  assert self.SideSlotHeight>0 and self.SideSlotTopMargin>0
  assert 0<self.SideSlotExternalWidth<self.SideSlotPitch and 0<self.SideSlotAngle<=90
  assert 0<self.FloorInnerRadius<self.OuterCornerRadius-self.Wall,'Floor radius must remain below inner plan corner radius for the current exact corner construction'
  assert self.GrooveWidth>=self.TongueWidth+self.JointGap-1e-9
  assert self.GrooveHeight>=self.TongueHeight+self.JointGap-1e-9
  assert abs(self.PCBTopZ-14.6)<1e-8
  return self
 def manifest(self):
  self.validate();return dict(asdict(self),SideSlotTopMargin=self.SideSlotTopMargin,PCBTopZ=self.PCBTopZ,CapRadius=self.CapRadius,CapApexZ=self.CapApexZ,PCBMounts=PCB_MOUNTS,CaseMounts=CASE_MOUNTS,FeetAxes=FEET_AXES)
DEFAULT=Parameters().validate()
