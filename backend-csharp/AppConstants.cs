namespace SchoolGuardian.Api
{
    /// <summary>
    /// Tập trung tất cả hằng số dùng chung trong toàn bộ ứng dụng.
    /// Mọi magic string đều nên được định nghĩa ở đây.
    /// </summary>
    public static class AppConstants
    {
        // ====================================================
        // Roles — phải khớp với enum Role trong ApplicationEntities.cs
        // ====================================================
        public static class Roles
        {
            public const string Admin       = "admin";
            public const string BanGiamHieu = "ban_giam_hieu";
            public const string GiamThi     = "giam_thi";
            public const string BaoVe       = "bao_ve";
            public const string PhuHuynh    = "phu_huynh";
        }

        // ====================================================
        // Alert offline sync actions
        // ====================================================
        public static class OfflineActions
        {
            public const string UpdateStatus = "update_status";
            public const string AddNote      = "add_note";
        }

        // ====================================================
        // Settings keys (dùng trong bảng settings của DB)
        // ====================================================
        public static class SettingKeys
        {
            public const string SimulatorEnabled = "simulator_enabled";
        }

        // ====================================================
        // Alert status action labels (dùng khi ghi AlertLog)
        // ====================================================
        public static class AlertActions
        {
            public const string Confirmed   = "Xác nhận sự cố";
            public const string FalseAlarm  = "Đánh dấu báo động giả";
            public const string Resolved    = "Đã xử lý xong";
        }

        // ====================================================
        // Sound type labels — text thuần, không chứa HTML
        // ====================================================
        public static class SoundLabels
        {
            public const string DapPha   = "Đập phá / Đánh đập";
            public const string Help     = "Kêu cứu / Van xin";
            public const string Threat   = "Đe dọa";
            public const string Scream   = "Gào thét / La hét";
            public const string Argument = "Cãi vã";
            public const string Unknown  = "Cảnh báo";
        }
    }
}
