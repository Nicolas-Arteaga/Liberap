using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Verge.Localization;
using Verge.MultiTenancy;
using Verge.Trading;
using Verge.Trading.Bot;
using Verge.Trading.DecisionEngine;
using Verge.Trading.Integrations;
using System;
using Volo.Abp.Localization;
using Volo.Abp.Timing;
using Volo.Abp.Modularity;
using Volo.Abp.MultiTenancy;
using Volo.Abp.PermissionManagement.Identity;
using Volo.Abp.SettingManagement;
using Volo.Abp.BlobStoring.Database;
using Volo.Abp.Caching;
using Volo.Abp.OpenIddict;
using Volo.Abp.PermissionManagement.OpenIddict;
using Volo.Abp.AuditLogging;
using Volo.Abp.BackgroundJobs;
using Volo.Abp.Emailing;
using Volo.Abp.FeatureManagement;
using Volo.Abp.Identity;
using Volo.Abp.TenantManagement;

namespace Verge;

[DependsOn(
    typeof(VergeDomainSharedModule),
    typeof(AbpAuditLoggingDomainModule),
    typeof(AbpCachingModule),
    typeof(AbpBackgroundJobsDomainModule),
    typeof(AbpFeatureManagementDomainModule),
    typeof(AbpPermissionManagementDomainIdentityModule),
    typeof(AbpPermissionManagementDomainOpenIddictModule),
    typeof(AbpSettingManagementDomainModule),
    typeof(AbpEmailingModule),
    typeof(AbpIdentityDomainModule),
    typeof(AbpOpenIddictDomainModule),
    typeof(AbpTenantManagementDomainModule),
    typeof(BlobStoringDatabaseDomainModule)
    )]
public class VergeDomainModule : AbpModule
{
    public override void ConfigureServices(ServiceConfigurationContext context)
    {
        Configure<AbpMultiTenancyOptions>(options =>
        {
            options.IsEnabled = MultiTenancyConsts.IsEnabled;
        });

        Configure<AbpClockOptions>(options =>
        {
            options.Kind = DateTimeKind.Utc;
        });

        context.Services.AddHttpClient();
        context.Services.AddTransient<CryptoAnalysisService>();
        context.Services.AddTransient<IProbabilisticEngine, ProbabilisticEngine>();
        context.Services.AddTransient<IMultiAgentConsensusService, MultiAgentConsensusService>();
        context.Services.AddScoped<IWhaleTrackerService, WhaleTrackerService>();
        context.Services.AddScoped<IInstitutionalDataService, InstitutionalDataService>();
        context.Services.AddSingleton<IMacroSentimentService, MacroSentimentService>();
        context.Services.AddSingleton<IFractalPatternManager, FractalPatternManager>();
        context.Services.AddSingleton<IAniquiladorPatternManager, AniquiladorPatternManager>();
        
        context.Services.AddSingleton<BinanceWebSocketService>();
        context.Services.AddHostedService(sp => sp.GetRequiredService<BinanceWebSocketService>());

        // ─── Bot de Scalping Agresivo ───
        context.Services.AddTransient<ScalpingSignalEngine>();
        context.Services.AddSingleton<IBotStateService, BotStateService>();
#if DEBUG
        context.Services.Replace(ServiceDescriptor.Singleton<IEmailSender, NullEmailSender>());
#endif
    }
}
