using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.Tokens;
using SchoolGuardian.Api.Data;
using SchoolGuardian.Api.Hubs;
using SchoolGuardian.Api.Models;
using SchoolGuardian.Api.Services;
using System.Text;


var builder = WebApplication.CreateBuilder(args);

// ============================================================
// 1. Database - Entity Framework Core with PostgreSQL
// ============================================================
var connStr = builder.Configuration.GetConnectionString("DefaultConnection")!;
var dataSourceBuilder = new Npgsql.NpgsqlDataSourceBuilder(connStr);
dataSourceBuilder.EnableUnmappedTypes();
var dataSource = dataSourceBuilder.Build();

try
{
    using (var connection = new Npgsql.NpgsqlConnection(connStr))
    {
        connection.Open();
        string alterScript = @"
            DO $$ 
            BEGIN 
                -- Change enum columns to text to avoid Npgsql mapping issues
                ALTER TABLE users ALTER COLUMN role TYPE text USING role::text;
                ALTER TABLE devices ALTER COLUMN status TYPE text USING status::text;
                ALTER TABLE alerts ALTER COLUMN sound_type TYPE text USING sound_type::text;
                ALTER TABLE alerts ALTER COLUMN status TYPE text USING status::text;
            EXCEPTION WHEN others THEN
                -- Ignore errors if columns are already text
            END $$;
        ";
        using var cmd = new Npgsql.NpgsqlCommand(alterScript, connection);
        cmd.ExecuteNonQuery();
    }
}
catch (Exception)
{
    // Ignore error if DB is not available at design-time (e.g., during migrations)
}

builder.Services.AddDbContext<ApplicationDbContext>(options =>
    options.UseNpgsql(dataSource));


// ============================================================
// 2. JWT Authentication (thay thế Passport-JWT của NestJS)
// ============================================================
var jwtSecret = builder.Configuration["Jwt:Secret"] ?? "changeme_secret_key_at_least_32_chars";
builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(options =>
    {
        options.TokenValidationParameters = new TokenValidationParameters
        {
            ValidateIssuerSigningKey = true,
            IssuerSigningKey = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(jwtSecret)),
            ValidateIssuer = false,
            ValidateAudience = false,
            ClockSkew = TimeSpan.Zero,
        };
        // Allow JWT via SignalR query string
        options.Events = new JwtBearerEvents
        {
            OnMessageReceived = context =>
            {
                var token = context.Request.Query["access_token"];
                if (!string.IsNullOrEmpty(token) && context.Request.Path.StartsWithSegments("/ws"))
                    context.Token = token;
                return Task.CompletedTask;
            }
        };
    });

// ============================================================
// 3. CORS - allow frontend to connect
// ============================================================
builder.Services.AddCors(options =>
{
    options.AddDefaultPolicy(policy =>
        policy.SetIsOriginAllowed(origin => true)
              .AllowAnyHeader()
              .AllowAnyMethod()
              .AllowCredentials());
});

// ============================================================
// 4. SignalR (thay thế Socket.IO của NestJS)
// ============================================================
builder.Services.AddSignalR()
    .AddJsonProtocol(options =>
    {
        options.PayloadSerializerOptions.PropertyNamingPolicy = System.Text.Json.JsonNamingPolicy.SnakeCaseLower;
    });

// ============================================================
// 5. Dependency Injection - Register all Services
// ============================================================
builder.Services.AddHttpClient();
builder.Services.AddSingleton<IPushNotificationService, PushNotificationService>();
builder.Services.AddScoped<AuthService>();
builder.Services.AddScoped<UsersService>();
builder.Services.AddScoped<AreasService>();
builder.Services.AddScoped<DevicesService>();
builder.Services.AddScoped<AlertsService>();
builder.Services.AddScoped<StatisticsService>();
builder.Services.AddScoped<SettingsService>();
builder.Services.AddScoped<ParentService>();
builder.Services.AddHostedService<SimulatorBackgroundService>();

// ============================================================
// 6. Controllers + OpenAPI
// ============================================================
builder.Services.AddControllers()
    .AddJsonOptions(options =>
    {
        options.JsonSerializerOptions.PropertyNamingPolicy = System.Text.Json.JsonNamingPolicy.SnakeCaseLower;
    });
builder.Services.AddOpenApi();

var app = builder.Build();

// ============================================================
// 7. Middleware pipeline
// ============================================================
if (app.Environment.IsDevelopment())
    app.MapOpenApi();

app.UseCors();
app.UseAuthentication();
app.UseAuthorization();

// Serve uploaded audio files statically (replace NestJS ServeStatic)
app.UseStaticFiles();

var uploadsPath = builder.Configuration["Storage:AudioPath"] ?? Path.Combine(Directory.GetCurrentDirectory(), "uploads");
if (!Directory.Exists(uploadsPath)) Directory.CreateDirectory(uploadsPath);

var provider = new Microsoft.AspNetCore.StaticFiles.FileExtensionContentTypeProvider();
if (!provider.Mappings.ContainsKey(".m4a"))
    provider.Mappings[".m4a"] = "audio/mp4";

app.UseStaticFiles(new StaticFileOptions
{
    FileProvider = new Microsoft.Extensions.FileProviders.PhysicalFileProvider(uploadsPath),
    RequestPath = "/uploads",
    ContentTypeProvider = provider,
    ServeUnknownFileTypes = true
});

var tailieuPath = builder.Configuration["Storage:AudioPath"] ?? uploadsPath;
if (!Directory.Exists(tailieuPath)) Directory.CreateDirectory(tailieuPath);
app.UseStaticFiles(new StaticFileOptions
{
    FileProvider = new Microsoft.Extensions.FileProviders.PhysicalFileProvider(tailieuPath),
    RequestPath = "/tai-lieu",
    ContentTypeProvider = provider,
    ServeUnknownFileTypes = true
});
var frontendPath = builder.Configuration["Frontend:Path"]
    ?? Path.Combine(Directory.GetCurrentDirectory(), "frontend");
if (!Directory.Exists(frontendPath))
{
    frontendPath = Path.Combine(Directory.GetCurrentDirectory(), "..", "frontend");
}

if (Directory.Exists(frontendPath))
{
    app.UseStaticFiles(new StaticFileOptions
    {
        FileProvider = new Microsoft.Extensions.FileProviders.PhysicalFileProvider(frontendPath),
        RequestPath = ""
    });
}

app.MapControllers();
app.MapGet("/health", async (ApplicationDbContext db) =>
    await db.Database.CanConnectAsync()
        ? Results.Ok(new { status = "healthy" })
        : Results.StatusCode(503));
app.MapGet("/", () => Results.Redirect("/dang-nhap.html"));

// SignalR Hub - Frontend kết nối tới /ws/alerts
// (tương đương namespace '/ws/alerts' của Socket.IO trong NestJS)
app.MapHub<AlertHub>("/ws/alerts");

// Auto-migrate and seed database
using (var scope = app.Services.CreateScope())
{
    var db = scope.ServiceProvider.GetRequiredService<ApplicationDbContext>();
    db.Database.EnsureCreated();
    db.Database.ExecuteSqlRaw(File.ReadAllText(
        Path.Combine(AppContext.BaseDirectory, "audio-analysis-schema.sql")));

    if (!db.Users.Any())
    {
        var admin = new User { Id = Guid.NewGuid().ToString(), FullName = "Admin", Email = "admin@gmail.com", PasswordHash = BCrypt.Net.BCrypt.HashPassword("password123"), Role = Role.admin };
        var bgh = new User { Id = Guid.NewGuid().ToString(), FullName = "Ban Giám Hiệu", Email = "bgh@gmail.com", PasswordHash = BCrypt.Net.BCrypt.HashPassword("password123"), Role = Role.ban_giam_hieu };
        var giamthi = new User { Id = Guid.NewGuid().ToString(), FullName = "Giám Thị", Email = "giamthi@gmail.com", PasswordHash = BCrypt.Net.BCrypt.HashPassword("password123"), Role = Role.giam_thi };
        var phuhuynh = new User { Id = Guid.NewGuid().ToString(), FullName = "Phụ Huynh A", Email = "phuhuynh@gmail.com", PasswordHash = BCrypt.Net.BCrypt.HashPassword("password123"), Role = Role.phu_huynh };

        db.Users.AddRange(admin, bgh, giamthi, phuhuynh);

        var area1 = new Area { Id = Guid.NewGuid().ToString(), Name = "Hành lang Tầng 1", Description = "Khu vực hành lang chính" };
        var area2 = new Area { Id = Guid.NewGuid().ToString(), Name = "Sân sau", Description = "Khu vực tập trung đông học sinh" };
        var classroom = new Area { Id = Guid.NewGuid().ToString(), Name = "Lớp 10A1", Description = "Phòng học chuẩn" };

        db.Areas.AddRange(area1, area2, classroom);

        var device1 = new Device { Id = Guid.NewGuid().ToString(), Name = "Cam-HL1", AreaId = area1.Id, Floor = 1, PositionX = 10.5, PositionY = 20.0, Status = DeviceStatus.online, BatteryLevel = 100 };
        var device2 = new Device { Id = Guid.NewGuid().ToString(), Name = "Cam-SS", AreaId = area2.Id, Floor = 1, PositionX = 5.0, PositionY = 50.0, Status = DeviceStatus.online, BatteryLevel = 90 };

        db.Devices.AddRange(device1, device2);

        var student = new Student { Id = Guid.NewGuid().ToString(), FullName = "Học sinh A", ParentId = phuhuynh.Id, ClassroomId = classroom.Id };

        db.Students.Add(student);

        db.SaveChanges();
    }
}

app.Run();
