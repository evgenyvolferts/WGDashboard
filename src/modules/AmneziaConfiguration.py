"""
AmneziaWG Configuration
"""
from .PeerJobs import PeerJobs
from .AmneziaPeer import AmneziaPeer
from .PeerShareLinks import PeerShareLinks
from .WireguardConfiguration import WireguardConfiguration
from .DashboardWebHooks import DashboardWebHooks


class AmneziaConfiguration(WireguardConfiguration):
    def __init__(self,
                 DashboardConfig,
                 AllPeerJobs: PeerJobs,
                 AllPeerShareLinks: PeerShareLinks,
                 DashboardWebHooks: DashboardWebHooks,
                 name: str = None,
                 data: dict = None,
                 backup: dict = None,
                 startup: bool = False):
        self.Jc = 0
        self.Jmin = 0
        self.Jmax = 0
        self.S1 = 0
        self.S2 = 0
        self.S3 = 0
        self.S4 = 0
        self.H1 = 1
        self.H2 = 2
        self.H3 = 3
        self.H4 = 4
        self.I1 = "0"
        self.I2 = "0"
        self.I3 = "0"
        self.I4 = "0"
        self.I5 = "0"
        self.HeaderProtectionKey = "0"
        self.ContentPaddingAddition = 0
        self.RekeyAfterTime = 0
        self.RekeyTimeout = 0
        self.RejectAfterTime = 0
        self.KeepaliveTimeout = 0
        self.MaxHandshakeAttempts = 0
        self.RandomTrailers = 0
        self.DisableCookies = 0

        super().__init__(DashboardConfig, AllPeerJobs, AllPeerShareLinks, DashboardWebHooks, name, data, backup, startup, wg=False)

    def toJson(self):
        self.Status = self.getStatus()
        return {
            "Status": self.Status,
            "Name": self.Name,
            "PrivateKey": self.PrivateKey,
            "PublicKey": self.PublicKey,
            "Address": self.Address,
            "ListenPort": self.ListenPort,
            "PreUp": self.PreUp,
            "PreDown": self.PreDown,
            "PostUp": self.PostUp,
            "PostDown": self.PostDown,
            "SaveConfig": self.SaveConfig,
            "Info": self.configurationInfo.model_dump(),
            "DataUsage": {
                "Total": sum(list(map(lambda x: x.cumu_data + x.total_data, self.Peers))),
                "Sent": sum(list(map(lambda x: x.cumu_sent + x.total_sent, self.Peers))),
                "Receive": sum(list(map(lambda x: x.cumu_receive + x.total_receive, self.Peers)))
            },
            "ConnectedPeers": len(list(filter(lambda x: x.status == "running", self.Peers))),
            "TotalPeers": len(self.Peers),
            "Protocol": self.Protocol,
            "Table": self.Table,
            "Jc": self.Jc,
            "Jmin": self.Jmin,
            "Jmax": self.Jmax,
            "S1": self.S1,
            "S2": self.S2,
            "S3": self.S3,
            "S4": self.S4,
            "H1": self.H1,
            "H2": self.H2,
            "H3": self.H3,
            "H4": self.H4,
            "I1": self.I1,
            "I2": self.I2,
            "I3": self.I3,
            "I4": self.I4,
            "I5": self.I5,
            "HeaderProtectionKey": self.HeaderProtectionKey,
            "ContentPaddingAddition": self.ContentPaddingAddition,
            "RekeyAfterTime": self.RekeyAfterTime,
            "RekeyTimeout": self.RekeyTimeout,
            "RejectAfterTime": self.RejectAfterTime,
            "KeepaliveTimeout": self.KeepaliveTimeout,
            "MaxHandshakeAttempts": self.MaxHandshakeAttempts,
            "RandomTrailers": self.RandomTrailers,
            "DisableCookies": self.DisableCookies
        }

    def _createPeer(self, data):
        return AmneziaPeer(data, self)
