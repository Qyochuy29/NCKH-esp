using Microsoft.EntityFrameworkCore;
using SchoolGuardian.Api.Models;

namespace SchoolGuardian.Api.Data
{
    public class ApplicationDbContext : DbContext
    {
        public ApplicationDbContext(DbContextOptions<ApplicationDbContext> options)
            : base(options)
        {
        }

        public DbSet<User> Users { get; set; }
        public DbSet<UserDevice> UserDevices { get; set; }
        public DbSet<Area> Areas { get; set; }
        public DbSet<Device> Devices { get; set; }
        public DbSet<Alert> Alerts { get; set; }
        public DbSet<AudioAnalysis> AudioAnalyses { get; set; }
        public DbSet<AlertLog> AlertLogs { get; set; }
        public DbSet<Setting> Settings { get; set; }
        public DbSet<Student> Students { get; set; }

        protected override void OnModelCreating(ModelBuilder modelBuilder)
        {
            base.OnModelCreating(modelBuilder);
            // modelBuilder.HasPostgresEnum<Role>("Role");
            // modelBuilder.HasPostgresEnum<DeviceStatus>("DeviceStatus");
            // modelBuilder.HasPostgresEnum<SoundType>("SoundType");

            // Unique constraints
            modelBuilder.Entity<User>()
                .HasIndex(u => u.Email)
                .IsUnique();
            modelBuilder.Entity<User>().Property(e => e.Role)
                .HasConversion<string>();
            modelBuilder.Entity<User>()
                .HasQueryFilter(u => u.IsActive);

            modelBuilder.Entity<Device>().Property(e => e.Status)
                .HasConversion<string>();
            modelBuilder.Entity<Device>()
                .HasQueryFilter(d => d.IsActive);
            modelBuilder.Entity<Device>()
                .HasIndex(d => d.AreaId);
            modelBuilder.Entity<Device>()
                .HasIndex(d => d.Status);

            modelBuilder.Entity<Alert>().Property(e => e.SoundType)
                .HasConversion<string>();
            modelBuilder.Entity<Alert>().Property(e => e.Status)
                .HasConversion<string>();

            modelBuilder.Entity<Area>()
                .HasIndex(a => a.Name)
                .IsUnique();
            modelBuilder.Entity<Area>()
                .HasQueryFilter(a => a.IsActive);

            // Indexes for Alerts
            modelBuilder.Entity<Alert>().HasIndex(a => a.Timestamp).IsDescending();
            modelBuilder.Entity<Alert>().HasIndex(a => a.Status);
            modelBuilder.Entity<Alert>().HasIndex(a => a.SoundType);
            modelBuilder.Entity<Alert>().HasIndex(a => new { a.Status, a.Timestamp }).IsDescending(false, true);
            modelBuilder.Entity<Alert>().HasIndex(a => new { a.DeviceId, a.Timestamp }).IsDescending(false, true);
            modelBuilder.Entity<Alert>().HasIndex(a => a.HandledById);

            // Indexes for AlertLogs
            modelBuilder.Entity<AlertLog>().HasIndex(al => new { al.AlertId, al.Timestamp });

            // Indexes for Students
            modelBuilder.Entity<Student>().HasIndex(s => s.ParentId);
            modelBuilder.Entity<Student>().HasIndex(s => s.ClassroomId);
            modelBuilder.Entity<Setting>()
                .HasIndex(s => s.Key)
                .IsUnique();

            // Explicit relationship configuration matching Prisma
            modelBuilder.Entity<Device>()
                .HasOne(d => d.Area)
                .WithMany(a => a.Devices)
                .HasForeignKey(d => d.AreaId)
                .OnDelete(DeleteBehavior.Restrict);

            modelBuilder.Entity<Alert>()
                .HasOne(a => a.Device)
                .WithMany(d => d.Alerts)
                .HasForeignKey(a => a.DeviceId)
                .OnDelete(DeleteBehavior.Restrict);

            modelBuilder.Entity<Alert>()
                .HasOne(a => a.HandledBy)
                .WithMany(u => u.HandledAlerts)
                .HasForeignKey(a => a.HandledById)
                .OnDelete(DeleteBehavior.Restrict);

            modelBuilder.Entity<AlertLog>()
                .HasOne(al => al.Alert)
                .WithMany(a => a.Logs)
                .HasForeignKey(al => al.AlertId)
                .OnDelete(DeleteBehavior.Cascade);

            modelBuilder.Entity<AlertLog>()
                .HasOne(al => al.Actor)
                .WithMany(u => u.AlertLogs)
                .HasForeignKey(al => al.ActorId)
                .OnDelete(DeleteBehavior.Restrict);

            modelBuilder.Entity<Student>()
                .HasOne(s => s.Parent)
                .WithMany()
                .HasForeignKey(s => s.ParentId)
                .OnDelete(DeleteBehavior.Restrict);

            modelBuilder.Entity<Student>()
                .HasOne(s => s.Classroom)
                .WithMany()
                .HasForeignKey(s => s.ClassroomId)
                .OnDelete(DeleteBehavior.Restrict);

            modelBuilder.Entity<UserDevice>()
                .HasOne(ud => ud.User)
                .WithMany(u => u.Devices)
                .HasForeignKey(ud => ud.UserId)
                .OnDelete(DeleteBehavior.Cascade);
        }
    }
}
