using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography.X509Certificates;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Cors;
using Microsoft.AspNetCore.HttpOverrides;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.AspNetCore.Extensions.DependencyInjection;
using OpenIddict.Validation.AspNetCore;
using OpenIddict.Server.AspNetCore;
using Verge.EntityFrameworkCore;
using Verge.MultiTenancy;
using Verge.Trading;
using Verge.Trading.BackgroundJobs;
using Microsoft.AspNetCore.SignalR;
using Verge.HealthChecks;
using Microsoft.OpenApi.Models;
using Volo.Abp;
using Volo.Abp.Studio;
using Volo.Abp.Account;
using Volo.Abp.Account.Web;
using Volo.Abp.AspNetCore.MultiTenancy;
using Volo.Abp.AspNetCore.Mvc;
using Volo.Abp.Autofac;
using Volo.Abp.Localization;
using Volo.Abp.Modularity;
using Volo.Abp.UI.Navigation.Urls;
using Volo.Abp.VirtualFileSystem;
using Volo.Abp.AspNetCore.Mvc.UI.Bundling;
using Volo.Abp.AspNetCore.Mvc.UI.Theme.Shared;
using Volo.Abp.AspNetCore.Mvc.UI.Theme.Basic;
using Volo.Abp.AspNetCore.Mvc.UI.Theme.Basic.Bundling;
using Microsoft.AspNetCore.Hosting;
using Volo.Abp.AspNetCore.Serilog;
using Volo.Abp.Identity;
using Volo.Abp.OpenIddict;
using Volo.Abp.Swashbuckle;
using Volo.Abp.Studio.Client.AspNetCore;
using Volo.Abp.Security.Claims;
using System.IdentityModel.Tokens.Jwt;
using Volo.Abp.AspNetCore.SignalR;
using StackExchange.Redis;
using Verge.BackgroundJobs;

namespace Verge;

[DependsOn(
    typeof(VergeHttpApiModule),
    typeof(AbpStudioClientAspNetCoreModule),
    typeof(AbpAspNetCoreMvcUiBasicThemeModule),
    typeof(AbpAutofacModule),
    typeof(AbpAspNetCoreMultiTenancyModule),
    typeof(VergeApplicationModule),
    typeof(VergeEntityFrameworkCoreModule),
    typeof(AbpAccountWebOpenIddictModule),
    typeof(AbpSwashbuckleModule),
    typeof(AbpAspNetCoreSerilogModule),
    typeof(AbpAspNetCoreSignalRModule)
    )]
public class VergeHttpApiHostModule : AbpModule
{
    public override void PreConfigureServices(ServiceConfigurationContext context)
    {
        var hostingEnvironment = context.Services.GetHostingEnvironment();
        var configuration = context.Services.GetConfiguration();

        PreConfigure<OpenIddictBuilder>(builder =>
        {
            builder.AddValidation(options =>
            {
                options.AddAudiences("Verge");
                options.UseLocalServer();
                options.UseAspNetCore();
            });
        });

        PreConfigure<OpenIddictServerBuilder>(builder =>
        {
            builder.SetAccessTokenLifetime(TimeSpan.FromHours(12));
            builder.SetRefreshTokenLifetime(TimeSpan.FromDays(30));
            builder.SetAuthorizationCodeLifetime(TimeSpan.FromMinutes(5));
        });

        if (!hostingEnvironment.IsDevelopment())
        {
            PreConfigure<AbpOpenIddictAspNetCoreOptions>(options =>
            {
                options.AddDevelopmentEncryptionAndSigningCertificate = false;
            });

            PreConfigure<OpenIddictServerBuilder>(serverBuilder =>
            {
                serverBuilder.AddProductionEncryptionAndSigningCertificate("openiddict.pfx", configuration["AuthServer:CertificatePassPhrase"]!);
                serverBuilder.SetIssuer(new Uri(configuration["AuthServer:Authority"]!));
            });
        }
    }

    public override void ConfigureServices(ServiceConfigurationContext context)
    {
        var configuration = context.Services.GetConfiguration();
        var hostingEnvironment = context.Services.GetHostingEnvironment();

        if (!configuration.GetValue<bool>("App:DisablePII"))
        {
            Microsoft.IdentityModel.Logging.IdentityModelEventSource.ShowPII = true;
            Microsoft.IdentityModel.Logging.IdentityModelEventSource.LogCompleteSecurityArtifact = true;
        }

        if (!configuration.GetValue<bool>("AuthServer:RequireHttpsMetadata"))
        {
            Configure<OpenIddictServerAspNetCoreOptions>(options =>
            {
                options.DisableTransportSecurityRequirement = true;
            });
            
            Configure<ForwardedHeadersOptions>(options =>
            {
                options.ForwardedHeaders = ForwardedHeaders.XForwardedProto;
            });
        }

        JwtSecurityTokenHandler.DefaultInboundClaimTypeMap.Clear();
        JwtSecurityTokenHandler.DefaultOutboundClaimTypeMap.Clear();

        ConfigureAuthentication(context);
        ConfigureUrls(configuration);
        ConfigureBundles();
        ConfigureConventionalControllers();
        ConfigureHealthChecks(context);
        ConfigureSwagger(context, configuration);
        ConfigureVirtualFileSystem(context);
        ConfigureCors(context, configuration);
        
        context.Services.AddSingleton<ITickSpikeAlerter, TickSpikeAlerter>();
        context.Services.AddHostedService<FastTickScannerService>();
        context.Services.AddHostedService<TradingSessionMonitorJob>();
        context.Services.AddHostedService<AutoCalibrationJob>();
        context.Services.AddHostedService<WhaleMonitoringJob>();
        context.Services.AddHostedService<MacroCalendarJob>();
        context.Services.AddHostedService<MarketScannerService>();
        context.Services.AddHostedService<LiveSignalCollectorJob>();
        context.Services.AddHostedService<SimulationMarkPriceWorker>();
        context.Services.AddHostedService<BotDataPublisherService>();
        context.Services.AddHostedService<BotSyncJob>();
        context.Services.AddHostedService<Verge.Trading.Nexus15.Nexus15ScannerJob>();
        context.Services.AddScoped<Verge.Trading.Nexus15.IPythonNexus15Service, Verge.Trading.Nexus15.PythonNexus15Service>();
        context.Services.AddScoped<Verge.Trading.Scar.IPythonScarService, Verge.Trading.Scar.PythonScarService>();


        // Redis Configuration (Graceful startup)
        var redisConfig = configuration["Redis:Configuration"] ?? "localhost:6379";
        if (!redisConfig.Contains("abortConnect")) 
        {
            redisConfig += redisConfig.Contains(",") ? ",abortConnect=false" : ",abortConnect=false";
        }
        
        context.Services.AddSingleton<IConnectionMultiplexer>(ConnectionMultiplexer.Connect(redisConfig));

        // Execution Service
        context.Services.AddSingleton<BinanceFuturesExecutionService>();

        context.Services.AddHttpClient("Freqtrade", client =>
        {
            var baseUrl = configuration["RemoteServices:Freqtrade:BaseUrl"] ?? "http://localhost:8080";
            client.BaseAddress = new Uri(baseUrl);
        });

        // Python AI Service HTTP Client
        context.Services.AddHttpClient<PythonIntegrationService>(client =>
        {
            var pythonUrl = configuration["PythonService:Url"] ?? "http://localhost:8000";
            client.BaseAddress = new Uri(pythonUrl);
            client.Timeout = TimeSpan.FromSeconds(10);
        });

        // Python Nexus 15 HTTP Client
        context.Services.AddHttpClient("PythonNexus15", client =>
        {
            var url = configuration["PythonService:Url"] ?? "http://localhost:8000";
            client.BaseAddress = new Uri(url);
            client.Timeout = TimeSpan.FromSeconds(30);
        });

        // Python SCAR HTTP Client
        context.Services.AddHttpClient("PythonScar", client =>
        {
            var url = configuration["PythonService:Url"] ?? "http://localhost:8000";
            client.BaseAddress = new Uri(url);
            client.Timeout = TimeSpan.FromSeconds(30);
        });


        context.Services.ConfigureApplicationCookie(options =>
        {
            options.ExpireTimeSpan = TimeSpan.FromDays(30);
            options.SlidingExpiration = true;
        });
    }

    private void ConfigureAuthentication(ServiceConfigurationContext context)
    {
        context.Services.ForwardIdentityAuthenticationForBearer(OpenIddictValidationAspNetCoreDefaults.AuthenticationScheme);

        // Fix SignalR Auth (Extract access_token from QueryString for WebSockets)
        context.Services.Configure<Microsoft.AspNetCore.Authentication.JwtBearer.JwtBearerOptions>(
            OpenIddictValidationAspNetCoreDefaults.AuthenticationScheme,
            options =>
            {
                var previousOnMessageReceived = options.Events?.OnMessageReceived;
                options.Events = new Microsoft.AspNetCore.Authentication.JwtBearer.JwtBearerEvents
                {
                    OnMessageReceived = async ctx =>
                    {
                        if (previousOnMessageReceived != null)
                        {
                            await previousOnMessageReceived(ctx);
                        }
                        
                        var accessToken = ctx.Request.Query["access_token"];
                        var path = ctx.HttpContext.Request.Path;
                        // Si la peticion es para nuestro hub
                        if (!string.IsNullOrEmpty(accessToken) && path.StartsWithSegments("/signalr-hubs"))
                        {
                            ctx.Token = accessToken;
                        }
                    }
                };
            });

        context.Services.Configure<AbpClaimsPrincipalFactoryOptions>(options =>
        {
            options.IsDynamicClaimsEnabled = true;
        });
    }

    private void ConfigureUrls(IConfiguration configuration)
    {
        Configure<AppUrlOptions>(options =>
        {
            options.Applications["MVC"].RootUrl = configuration["App:SelfUrl"];
            options.Applications["Angular"].RootUrl = configuration["App:AngularUrl"];
            options.Applications["Angular"].Urls[AccountUrlNames.PasswordReset] = "account/reset-password";
            options.RedirectAllowedUrls.AddRange(configuration["App:RedirectAllowedUrls"]?.Split(',') ?? Array.Empty<string>());
        });
    }

    private void ConfigureBundles()
    {
        Configure<AbpBundlingOptions>(options =>
        {
            options.StyleBundles.Configure(
                BasicThemeBundles.Styles.Global,
                bundle =>
                {
                    bundle.AddFiles("/global-styles.css");
                }
            );

            options.ScriptBundles.Configure(
                BasicThemeBundles.Scripts.Global,
                bundle =>
                {
                    bundle.AddFiles("/global-scripts.js");
                }
            );
        });
    }


    private void ConfigureVirtualFileSystem(ServiceConfigurationContext context)
    {
        var hostingEnvironment = context.Services.GetHostingEnvironment();

        if (hostingEnvironment.IsDevelopment())
        {
            Configure<AbpVirtualFileSystemOptions>(options =>
            {
                var sharedPath = Path.Combine(hostingEnvironment.ContentRootPath, $"..{Path.DirectorySeparatorChar}Verge.Domain.Shared");
                if (Directory.Exists(sharedPath))
                {
                    options.FileSets.ReplaceEmbeddedByPhysical<VergeDomainSharedModule>(sharedPath);
                }

                var domainPath = Path.Combine(hostingEnvironment.ContentRootPath, $"..{Path.DirectorySeparatorChar}Verge.Domain");
                if (Directory.Exists(domainPath))
                {
                    options.FileSets.ReplaceEmbeddedByPhysical<VergeDomainModule>(domainPath);
                }

                var contractsPath = Path.Combine(hostingEnvironment.ContentRootPath, $"..{Path.DirectorySeparatorChar}Verge.Application.Contracts");
                if (Directory.Exists(contractsPath))
                {
                    options.FileSets.ReplaceEmbeddedByPhysical<VergeApplicationContractsModule>(contractsPath);
                }

                var appPath = Path.Combine(hostingEnvironment.ContentRootPath, $"..{Path.DirectorySeparatorChar}Verge.Application");
                if (Directory.Exists(appPath))
                {
                    options.FileSets.ReplaceEmbeddedByPhysical<VergeApplicationModule>(appPath);
                }
            });
        }
    }

    private void ConfigureConventionalControllers()
    {
        Configure<AbpAspNetCoreMvcOptions>(options =>
        {
            options.ConventionalControllers.Create(typeof(VergeApplicationModule).Assembly);
        });
    }

    private static void ConfigureSwagger(ServiceConfigurationContext context, IConfiguration configuration)
    {
        context.Services.AddAbpSwaggerGenWithOidc(
            configuration["AuthServer:Authority"]!,
            ["Verge"],
            [AbpSwaggerOidcFlows.AuthorizationCode],
            null,
            options =>
            {
                options.SwaggerDoc("v1", new OpenApiInfo { Title = "Verge API", Version = "v1" });
                options.DocInclusionPredicate((docName, description) => true);
                options.CustomSchemaIds(type => type.FullName);
            });
    }

    private void ConfigureCors(ServiceConfigurationContext context, IConfiguration configuration)
    {
        context.Services.AddCors(options =>
        {
            options.AddDefaultPolicy(builder =>
            {
                builder
                    .WithOrigins("http://localhost:4200", "https://localhost:4200")
                    .WithAbpExposedHeaders()
                    .SetIsOriginAllowedToAllowWildcardSubdomains()
                    .AllowAnyHeader()
                    .AllowAnyMethod()
                    .AllowCredentials();
            });
            // Named policy specifically for SignalR (MapHub.RequireCors needs a named policy)
            options.AddPolicy("SignalRCors", builder =>
            {
                builder
                    .WithOrigins("http://localhost:4200", "https://localhost:4200")
                    .AllowAnyHeader()
                    .AllowAnyMethod()
                    .AllowCredentials();
            });
        });
    }

    private void ConfigureHealthChecks(ServiceConfigurationContext context)
    {
        context.Services.AddVergeHealthChecks();
    }

    public override void OnApplicationInitialization(ApplicationInitializationContext context)
    {
        var app = context.GetApplicationBuilder();
        var env = context.GetEnvironment();

        app.UseForwardedHeaders();

        if (env.IsDevelopment())
        {
            app.UseDeveloperExceptionPage();
        }

        app.UseAbpRequestLocalization();

        if (!env.IsDevelopment())
        {
            app.UseErrorPage();
        }

        app.UseCors();
        app.UseRouting();

        // Middleware para inyectar token de SignalR a los headers para que OpenIddict lo tome
        app.Use(async (context, next) =>
        {
            try
            {
                if (context.Request.Path.StartsWithSegments("/signalr-hubs") &&
                    context.Request.Query.TryGetValue("access_token", out var token))
                {
                    context.Request.Headers.Authorization = $"Bearer {token}";
                }
                await next();
            }
            catch (Exception ex) when (ex is System.IO.IOException || ex is OperationCanceledException)
            {
                // Silently swallow aborted requests during refresh/navigation
            }
        });

        app.MapAbpStaticAssets();
        app.UseAbpStudioLink();
        app.UseAbpSecurityHeaders();
        app.UseAuthentication();
        app.UseAbpOpenIddictValidation();

        if (MultiTenancyConsts.IsEnabled)
        {
            app.UseMultiTenancy();
        }

        app.UseUnitOfWork();
        app.UseDynamicClaims();
        app.UseAuthorization();

        app.UseSwagger();
        app.UseAbpSwaggerUI(options =>
        {
            options.SwaggerEndpoint("/swagger/v1/swagger.json", "Verge API");

            var configuration = context.ServiceProvider.GetRequiredService<IConfiguration>();
            options.OAuthClientId(configuration["AuthServer:SwaggerClientId"]);
        });
        app.UseAuditing();
        app.UseAbpSerilogEnrichers();
        app.UseConfiguredEndpoints();
    }
}
