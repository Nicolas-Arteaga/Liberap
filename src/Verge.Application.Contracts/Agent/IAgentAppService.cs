using System.Threading.Tasks;
using Volo.Abp.Application.Services;

namespace Verge.Agent;

public interface IAgentAppService : IApplicationService
{
    Task StartServerAsync();
    Task StopServerAsync();
    Task StartAgentAsync();
    Task StopAgentAsync();
}
