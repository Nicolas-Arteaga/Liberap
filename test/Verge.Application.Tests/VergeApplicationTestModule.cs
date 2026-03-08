using Volo.Abp.Modularity;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.AspNetCore.SignalR;
using NSubstitute;
using Verge.Trading;

namespace Verge;

[DependsOn(
    typeof(VergeApplicationModule),
    typeof(VergeDomainTestModule)
)]
public class VergeApplicationTestModule : AbpModule
{
    public override void ConfigureServices(ServiceConfigurationContext context)
    {
        context.Services.AddSingleton(Substitute.For<IHubContext<TradingHub>>());
    }
}
