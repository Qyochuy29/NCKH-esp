using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace SchoolGuardian.Api.Models
{
    public enum Role
    {
        admin,
        ban_giam_hieu,
        giam_thi,
        bao_ve,
        phu_huynh
    }

    public enum DeviceStatus
    {
        online,
        offline,
        error
    }

    public enum SoundType
    {
        scream,
        help,
        threat,
        argument,
        dap_pha
    }

    public enum AlertStatus
    {
        pending,
        confirmed,
        false_alarm,
        resolved
    }

    [Table("users")]
    public class User
    {
        [Key]
        [Column("id")]
        public string Id { get; set; } = Guid.NewGuid().ToString();

        [Required]
        [Column("full_name")]
        public string FullName { get; set; }

        [Required]
        [Column("email")]
        public string Email { get; set; }

        [Required]
        [Column("password_hash")]
        public string PasswordHash { get; set; }

        [Column("role")]
        public Role Role { get; set; }

        [Column("created_at")]
        public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

        [Column("is_active")]
        public bool IsActive { get; set; } = true;

        [InverseProperty("User")]
        public ICollection<UserDevice> Devices { get; set; }

        [InverseProperty("HandledBy")]
        public ICollection<Alert> HandledAlerts { get; set; }

        public ICollection<AlertLog> AlertLogs { get; set; }
    }

    [Table("user_devices")]
    public class UserDevice
    {
        [Key]
        [Column("id")]
        public string Id { get; set; } = Guid.NewGuid().ToString();

        [Required]
        [Column("user_id")]
        public string UserId { get; set; }

        [Required]
        [Column("fcm_token")]
        public string FcmToken { get; set; }

        [Column("device_name")]
        public string? DeviceName { get; set; }

        [Column("last_active")]
        public DateTime LastActive { get; set; } = DateTime.UtcNow;

        [ForeignKey("UserId")]
        public User User { get; set; }
    }

    [Table("areas")]
    public class Area
    {
        [Key]
        [Column("id")]
        public string Id { get; set; } = Guid.NewGuid().ToString();

        [Required]
        [Column("name")]
        public string Name { get; set; }

        [Column("description")]
        public string? Description { get; set; }

        [Column("created_at")]
        public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

        [Column("is_active")]
        public bool IsActive { get; set; } = true;

        public ICollection<Device> Devices { get; set; }
    }

    [Table("devices")]
    public class Device
    {
        [Key]
        [Column("id")]
        public string Id { get; set; } = Guid.NewGuid().ToString();

        [Required]
        [Column("name")]
        public string Name { get; set; }

        [Required]
        [Column("area_id")]
        public string AreaId { get; set; }

        [Column("floor")]
        public int Floor { get; set; }

        [Column("position_x")]
        public double PositionX { get; set; }

        [Column("position_y")]
        public double PositionY { get; set; }

        [Column("status")]
        public DeviceStatus Status { get; set; } = DeviceStatus.online;

        [Column("battery_level")]
        public int BatteryLevel { get; set; } = 100;

        [Column("last_seen")]
        public DateTime LastSeen { get; set; } = DateTime.UtcNow;

        [Column("is_active")]
        public bool IsActive { get; set; } = true;

        [ForeignKey("AreaId")]
        public Area Area { get; set; }

        public ICollection<Alert> Alerts { get; set; }
    }

    [Table("alerts")]
    public class Alert
    {
        [Key]
        [Column("id")]
        public string Id { get; set; } = Guid.NewGuid().ToString();

        [Required]
        [Column("device_id")]
        public string DeviceId { get; set; }

        [Column("timestamp")]
        public DateTime Timestamp { get; set; } = DateTime.UtcNow;

        [Column("sound_type")]
        public SoundType SoundType { get; set; }

        [Column("confidence_score")]
        public double ConfidenceScore { get; set; }

        [Column("audio_file_url")]
        public string? AudioFileUrl { get; set; }

        [Column("audio_data")]
        public byte[]? AudioData { get; set; }

        [Column("dialog_data")]
        public string? DialogData { get; set; }

        [Column("status")]
        public AlertStatus Status { get; set; } = AlertStatus.pending;

        [Column("handled_by_id")]
        public string? HandledById { get; set; }

        [Column("resolved_at")]
        public DateTime? ResolvedAt { get; set; }

        [Column("notes")]
        public string? Notes { get; set; }

        [Column("is_evidence")]
        public bool IsEvidence { get; set; } = false;

        [Column("transcript")]
        public string? Transcript { get; set; }

        [Column("keywords")]
        public string? Keywords { get; set; }

        [Column("timestamp_seconds")]
        public double? TimestampSeconds { get; set; }

        [ForeignKey("DeviceId")]
        public Device Device { get; set; }

        [ForeignKey("HandledById")]
        public User? HandledBy { get; set; }

        public ICollection<AlertLog> Logs { get; set; }
    }

    [Table("alert_logs")]
    public class AlertLog
    {
        [Key]
        [Column("id")]
        public string Id { get; set; } = Guid.NewGuid().ToString();

        [Required]
        [Column("alert_id")]
        public string AlertId { get; set; }

        [Required]
        [Column("action")]
        public string Action { get; set; }

        [Required]
        [Column("actor_id")]
        public string ActorId { get; set; }

        [Column("timestamp")]
        public DateTime Timestamp { get; set; } = DateTime.UtcNow;

        [ForeignKey("AlertId")]
        public Alert Alert { get; set; }

        [ForeignKey("ActorId")]
        public User Actor { get; set; }
    }

    [Table("settings")]
    public class Setting
    {
        [Key]
        [Column("key")]
        public string Key { get; set; }

        [Required]
        [Column("value")]
        public string Value { get; set; }
    }

    [Table("students")]
    public class Student
    {
        [Key]
        [Column("id")]
        public string Id { get; set; } = Guid.NewGuid().ToString();

        [Required]
        [Column("full_name")]
        public string FullName { get; set; }

        [Required]
        [Column("parent_id")]
        public string ParentId { get; set; }

        [Required]
        [Column("classroom_id")]
        public string ClassroomId { get; set; }

        [Column("created_at")]
        public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

        [ForeignKey("ParentId")]
        public User Parent { get; set; }

        [ForeignKey("ClassroomId")]
        public Area Classroom { get; set; }
    }
}
