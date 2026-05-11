using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Verge.Trading.DTOs;
using Volo.Abp.Application.Services;

namespace Verge.Trading;

public interface IStrategyProfileAppService : IApplicationService
{
    Task<List<StrategyProfileDto>> GetListAsync();
    Task<StrategyProfileDto> GetAsync(Guid id);
    Task<StrategyProfileDto> CreateAsync(CreateUpdateStrategyProfileDto input);
    Task<StrategyProfileDto> UpdateAsync(Guid id, CreateUpdateStrategyProfileDto input);
    Task DeleteAsync(Guid id);
    Task<StrategyProfileDto> ToggleActiveAsync(Guid id);
}
