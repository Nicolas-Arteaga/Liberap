using System.Collections.Generic;
using System.Threading.Tasks;
using Volo.Abp.Application.Services;

namespace Verge.Trading;

public interface IBotAppService : IApplicationService
{
    Task<List<BotPairDto>> GetActivePairsAsync();
}
